"""Workflow state machine. Every public method checks the actor's role and the
current status, applies the change, and writes an audit event in the same transaction."""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from engine.reviewer import Reviewer
from workflow import audit
from workflow.models import (
    Decision, Finding, FindingFeedback, FindingResponse, Submission, Version, utcnow,
)

# Statuses
SUBMITTED = "SUBMITTED"
AI_REVIEWED = "AI_REVIEWED"
PENDING_COMPLIANCE = "PENDING_COMPLIANCE"
APPROVED = "APPROVED"
RETURNED = "RETURNED"
REJECTED = "REJECTED"
FINAL_STATUSES = {APPROVED, REJECTED}

# Roles
MARKETING = "marketing"
COMPLIANCE = "compliance"
SYSTEM = "system"
AI_ACTOR = "ai-engine"

CHANNELS = ["email", "social", "web", "print", "radio", "mailer"]
PRODUCT_TYPES = ["deposit", "loan", "mortgage", "credit_card", "investment", "general"]
DECISIONS = {APPROVED, RETURNED, REJECTED}


@dataclass(frozen=True)
class User:
    name: str
    role: str


class WorkflowError(Exception):
    pass


class PermissionDenied(WorkflowError):
    pass


class InvalidTransition(WorkflowError):
    pass


class ValidationFailed(WorkflowError):
    pass


class GateBlocked(WorkflowError):
    def __init__(self, blockers: list[str]):
        super().__init__("Cannot send to Compliance: " + "; ".join(blockers))
        self.blockers = blockers


def _require_role(actor: User, role: str, action: str) -> None:
    if actor.role != role:
        raise PermissionDenied(f"{actor.name} ({actor.role}) is not allowed to {action}.")


def _require_status(sub: Submission, allowed: set[str], action: str) -> None:
    if sub.status not in allowed:
        raise InvalidTransition(f"Cannot {action} while {sub.id} is {sub.status}.")


def _require_text(value: str | None, what: str) -> str:
    if value is None or not value.strip():
        raise ValidationFailed(f"{what} is required.")
    return value.strip()


class WorkflowService:
    def __init__(self, session_factory: sessionmaker, reviewer_factory: Callable[[], Reviewer]):
        self._sessions = session_factory
        self._reviewer_factory = reviewer_factory
        self._reviewer: Reviewer | None = None

    def _get_reviewer(self) -> Reviewer:
        if self._reviewer is None:
            self._reviewer = self._reviewer_factory()
        return self._reviewer

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _load(session: Session, submission_id: str) -> Submission:
        sub = session.get(Submission, submission_id)
        if sub is None:
            raise WorkflowError(f"Submission {submission_id} not found.")
        return sub

    @staticmethod
    def _current_version(sub: Submission) -> Version:
        return sub.versions[-1]

    def _set_status(self, session: Session, sub: Submission, new: str, actor: User, action: str,
                    details: dict | None = None, **ai) -> None:
        old = sub.status
        sub.status = new
        audit.record(session, actor=actor.name, role=actor.role, action=action, submission_id=sub.id,
                     version_number=self._current_version(sub).number if sub.versions else None,
                     from_status=old, to_status=new, details=details, **ai)

    # ------------------------------------------------------------------ step 1
    def submit(self, actor: User, title: str, channel: str, product_type: str, content: str) -> str:
        _require_role(actor, MARKETING, "submit a marketing piece")
        title = _require_text(title, "Title")
        content = _require_text(content, "Content")
        if channel not in CHANNELS:
            raise ValidationFailed(f"Channel must be one of {CHANNELS}.")
        if product_type not in PRODUCT_TYPES:
            raise ValidationFailed(f"Product type must be one of {PRODUCT_TYPES}.")

        with self._sessions.begin() as s:
            n = s.scalar(select(func.count()).select_from(Submission)) or 0
            sub = Submission(id=f"SUB-{n + 1:04d}", title=title, channel=channel,
                             product_type=product_type, status=SUBMITTED, created_by=actor.name)
            s.add(sub)
            s.add(Version(submission=sub, number=1, content=content, created_by=actor.name))
            s.flush()
            audit.record(s, actor=actor.name, role=actor.role, action="submitted", submission_id=sub.id,
                         version_number=1, from_status=None, to_status=SUBMITTED,
                         details={"title": title, "channel": channel, "product_type": product_type})
            sub_id = sub.id
        self._run_ai_review(sub_id)
        return sub_id

    # ------------------------------------------------------------------ AI review
    def _run_ai_review(self, submission_id: str) -> None:
        system_user = User(AI_ACTOR, SYSTEM)
        with self._sessions.begin() as s:
            sub = self._load(s, submission_id)
            version = self._current_version(sub)
            try:
                result = self._get_reviewer().review(version.content, sub.channel, sub.product_type)
            except Exception as exc:  # LLM down, bad key, unparseable output: stay in SUBMITTED
                version.ai_error = str(exc)
                audit.record(s, actor=AI_ACTOR, role=SYSTEM, action="ai_review_failed",
                             submission_id=sub.id, version_number=version.number,
                             details={"error": str(exc)})
                return
            version.ai_error = None
            version.reviewed_at = utcnow()
            version.ai_provider = result.provider
            version.ai_model = result.model
            version.prompt_version = result.prompt_version
            version.taxonomy_version = result.taxonomy_version
            for f in result.findings:
                s.add(Finding(version=version, **f.model_dump()))
            self._set_status(
                s, sub, AI_REVIEWED, system_user, "ai_review_completed",
                details={
                    "findings": [f.issue_code for f in result.findings],
                    "high": sum(f.severity == "high" for f in result.findings),
                    "needs_human_review": sum(f.needs_human_review for f in result.findings),
                    "dropped_by_validation": len(result.dropped),
                    "classification": result.classification,
                    "latency_ms": result.latency_ms,
                    "provider": result.provider,
                },
                ai_model=result.model, prompt_version=result.prompt_version,
            )

    def retry_ai_review(self, actor: User, submission_id: str) -> None:
        _require_role(actor, MARKETING, "retry the AI review")
        with self._sessions.begin() as s:
            sub = self._load(s, submission_id)
            _require_status(sub, {SUBMITTED}, "retry the AI review")
            audit.record(s, actor=actor.name, role=actor.role, action="ai_review_retry_requested",
                         submission_id=sub.id, version_number=self._current_version(sub).number)
        self._run_ai_review(submission_id)

    # ------------------------------------------------------------------ step 2
    def respond(self, actor: User, finding_id: int, action: str, reason: str | None = None) -> None:
        _require_role(actor, MARKETING, "respond to findings")
        if action not in {"accept", "dispute"}:
            raise ValidationFailed("Response must be 'accept' or 'dispute'.")
        if action == "dispute":
            reason = _require_text(reason, "A reason for the dispute")
        with self._sessions.begin() as s:
            finding = s.get(Finding, finding_id)
            if finding is None:
                raise WorkflowError(f"Finding {finding_id} not found.")
            sub = finding.version.submission
            _require_status(sub, {AI_REVIEWED}, "respond to findings")
            if finding.version.id != self._current_version(sub).id:
                raise InvalidTransition("Only findings on the current version can be answered.")
            s.add(FindingResponse(finding_id=finding.id, action=action,
                                  reason=(reason or "").strip() or None, actor=actor.name))
            audit.record(s, actor=actor.name, role=actor.role,
                         action={"accept": "finding_accepted", "dispute": "finding_disputed"}[action],
                         submission_id=sub.id, version_number=finding.version.number,
                         details={"finding_id": finding.id, "issue_code": finding.issue_code,
                                  "severity": finding.severity, "reason": reason})

    def resubmit(self, actor: User, submission_id: str, content: str) -> int:
        _require_role(actor, MARKETING, "resubmit a revised version")
        content = _require_text(content, "Content")
        with self._sessions.begin() as s:
            sub = self._load(s, submission_id)
            _require_status(sub, {AI_REVIEWED, RETURNED}, "resubmit")
            current = self._current_version(sub)
            if content.strip() == current.content.strip():
                raise ValidationFailed("The revised version is identical to the current one.")
            new = Version(submission=sub, number=current.number + 1, content=content, created_by=actor.name)
            s.add(new)
            s.flush()
            self._set_status(s, sub, SUBMITTED, actor, "resubmitted",
                             details={"from_version": current.number, "to_version": new.number})
            number = new.number
        self._run_ai_review(submission_id)
        return number

    def gate_blockers(self, submission_id: str) -> list[str]:
        """Why the piece can't go to Compliance yet. Empty list = allowed.
        A high finding passes the gate only if it is disputed with a reason; an accepted
        high finding means 'I will fix it', so the marketer must revise and resubmit."""
        with self._sessions() as s:
            sub = self._load(s, submission_id)
            if sub.status != AI_REVIEWED:
                return [f"status is {sub.status}, not {AI_REVIEWED}"]
            blockers = []
            for f in self._current_version(sub).findings:
                if f.severity != "high":
                    continue
                r = f.latest_response
                if r is None:
                    blockers.append(f"{f.issue_code}: high finding has no response")
                elif r.action == "accept":
                    blockers.append(f"{f.issue_code}: accepted but not yet fixed; revise and resubmit")
            return blockers

    def send_to_compliance(self, actor: User, submission_id: str) -> None:
        _require_role(actor, MARKETING, "send to Compliance")
        blockers = self.gate_blockers(submission_id)
        if blockers:
            raise GateBlocked(blockers)
        with self._sessions.begin() as s:
            sub = self._load(s, submission_id)
            findings = self._current_version(sub).findings
            self._set_status(s, sub, PENDING_COMPLIANCE, actor, "sent_to_compliance", details={
                "disputed": [f.issue_code for f in findings if f.latest_response and f.latest_response.action == "dispute"],
                "accepted": [f.issue_code for f in findings if f.latest_response and f.latest_response.action == "accept"],
                "unanswered": [f.issue_code for f in findings if f.latest_response is None],
            })

    # ------------------------------------------------------------------ step 3
    def decide(self, actor: User, submission_id: str, decision: str, comment: str | None = None) -> None:
        _require_role(actor, COMPLIANCE, "make a compliance decision")
        if decision not in DECISIONS:
            raise ValidationFailed(f"Decision must be one of {sorted(DECISIONS)}.")
        if decision in {RETURNED, REJECTED}:
            comment = _require_text(comment, f"A comment for {decision.lower()}")
        with self._sessions.begin() as s:
            sub = self._load(s, submission_id)
            _require_status(sub, {PENDING_COMPLIANCE}, "decide")
            version = self._current_version(sub)
            s.add(Decision(submission_id=sub.id, version_number=version.number, decision=decision,
                           comment=(comment or "").strip() or None, actor=actor.name))
            self._set_status(s, sub, decision, actor, f"decision_{decision.lower()}",
                             details={"comment": comment}, ai_model=version.ai_model,
                             prompt_version=version.prompt_version)

    def give_feedback(self, actor: User, finding_id: int, verdict: str, note: str | None = None) -> None:
        _require_role(actor, COMPLIANCE, "rate AI findings")
        if verdict not in {"correct", "incorrect"}:
            raise ValidationFailed("Verdict must be 'correct' or 'incorrect'.")
        with self._sessions.begin() as s:
            finding = s.get(Finding, finding_id)
            if finding is None:
                raise WorkflowError(f"Finding {finding_id} not found.")
            sub = finding.version.submission
            _require_status(sub, {PENDING_COMPLIANCE, APPROVED, RETURNED, REJECTED}, "rate findings")
            s.add(FindingFeedback(finding_id=finding.id, verdict=verdict,
                                  note=(note or "").strip() or None, actor=actor.name))
            audit.record(s, actor=actor.name, role=actor.role, action="finding_feedback",
                         submission_id=sub.id, version_number=finding.version.number,
                         details={"finding_id": finding.id, "issue_code": finding.issue_code,
                                  "verdict": verdict, "note": note},
                         ai_model=finding.version.ai_model, prompt_version=finding.version.prompt_version)

    # ------------------------------------------------------------------ queries
    def get(self, submission_id: str) -> Submission:
        with self._sessions() as s:
            sub = s.scalars(
                select(Submission).where(Submission.id == submission_id).options(
                    selectinload(Submission.versions).selectinload(Version.findings)
                    .selectinload(Finding.responses),
                    selectinload(Submission.versions).selectinload(Version.findings)
                    .selectinload(Finding.feedback),
                    selectinload(Submission.decisions),
                )
            ).first()
            if sub is None:
                raise WorkflowError(f"Submission {submission_id} not found.")
            return sub

    def list_submissions(self, statuses: set[str] | None = None) -> list[Submission]:
        with self._sessions() as s:
            q = select(Submission).order_by(Submission.created_at.desc())
            if statuses:
                q = q.where(Submission.status.in_(statuses))
            return list(s.scalars(q))

    def audit_log(self, submission_id: str):
        with self._sessions() as s:
            return audit.events_for(s, submission_id)

    def verify_audit_chain(self) -> tuple[bool, int | None]:
        with self._sessions() as s:
            return audit.verify_chain(s)

    def diff(self, submission_id: str, from_version: int, to_version: int) -> str:
        sub = self.get(submission_id)
        by_num = {v.number: v for v in sub.versions}
        a, b = by_num[from_version].content, by_num[to_version].content
        return "\n".join(difflib.unified_diff(
            a.splitlines(), b.splitlines(), f"v{from_version}", f"v{to_version}", lineterm=""))
