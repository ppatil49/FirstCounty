"""Append-only, hash-chained audit trail. There is deliberately no update or delete function."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from workflow.models import AuditEvent, utcnow

GENESIS = "0" * 64


def _digest(prev_hash: str, fields: dict) -> str:
    payload = json.dumps(fields, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(f"{prev_hash}|{payload}".encode()).hexdigest()


def _hash_fields(e: AuditEvent) -> dict:
    return {
        # SQLite drops tzinfo on read, so hash the naive UTC form to verify identically later.
        "at": e.at.replace(tzinfo=None).isoformat() if e.at else None, "actor": e.actor, "role": e.role, "action": e.action,
        "submission_id": e.submission_id, "version_number": e.version_number,
        "from_status": e.from_status, "to_status": e.to_status, "details": e.details,
        "ai_model": e.ai_model, "prompt_version": e.prompt_version,
    }


def record(
    session: Session, *, actor: str, role: str, action: str, submission_id: str | None = None,
    version_number: int | None = None, from_status: str | None = None, to_status: str | None = None,
    details: dict | None = None, ai_model: str | None = None, prompt_version: str | None = None,
) -> AuditEvent:
    last = session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1)).first()
    prev_hash = last.hash if last else GENESIS
    event = AuditEvent(
        at=utcnow().replace(microsecond=0), actor=actor, role=role, action=action,
        submission_id=submission_id, version_number=version_number, from_status=from_status,
        to_status=to_status, details=details or {}, ai_model=ai_model, prompt_version=prompt_version,
        prev_hash=prev_hash,
    )
    event.hash = _digest(prev_hash, _hash_fields(event))
    session.add(event)
    session.flush()
    return event


def events_for(session: Session, submission_id: str) -> list[AuditEvent]:
    return list(session.scalars(
        select(AuditEvent).where(AuditEvent.submission_id == submission_id).order_by(AuditEvent.id)
    ))


def verify_chain(session: Session) -> tuple[bool, int | None]:
    """Recompute every hash. Returns (ok, id of first broken event)."""
    prev = GENESIS
    for e in session.scalars(select(AuditEvent).order_by(AuditEvent.id)):
        if e.prev_hash != prev or e.hash != _digest(prev, _hash_fields(e)):
            return False, e.id
        prev = e.hash
    return True, None
