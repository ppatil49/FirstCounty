"""Shared test data and helpers."""
from __future__ import annotations

from tests.fakes.fake_llm import finding
from workflow.service import COMPLIANCE, MARKETING, User

MARIA = User("maria", MARKETING)
CHRIS = User("chris", COMPLIANCE)

BAD_AD = "12-Month CD Special. Earn 4.25%! Limited time offer."
FIXED_AD = "12-Month CD Special. Earn 4.25% APY. Member FDIC. Rate accurate as of Nov 1, 2026."


def default_responder(prompt: str) -> list[dict]:
    """Flags a high-severity rate issue and a low one while 'Earn 4.25%!' is present; clean otherwise."""
    if "Earn 4.25%!" in prompt:
        return [finding("REGDD_RATE_NOT_APY", "Earn 4.25%!"),
                finding("UDAAP_MISLEADING", "Limited time offer.", severity="low", confidence=0.4)]
    return []


def finding_ids(service, sub_id, severity=None) -> list[int]:
    sub = service.get(sub_id)
    return [f.id for f in sub.versions[-1].findings if severity is None or f.severity == severity]


def to_pending(service, sub_id) -> None:
    for fid in finding_ids(service, sub_id, "high"):
        service.respond(MARIA, fid, "dispute", "Rate is labelled APY on the reverse side")
    service.send_to_compliance(MARIA, sub_id)
