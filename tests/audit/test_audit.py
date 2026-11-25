import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError

from tests.helpers import CHRIS, FIXED_AD, MARIA, to_pending
from workflow.models import AuditEvent, AuditImmutableError
from workflow.service import APPROVED, RETURNED


def full_journey(service, sid):
    to_pending(service, sid)
    service.decide(CHRIS, sid, RETURNED, "Add APY disclosures")
    service.resubmit(MARIA, sid, FIXED_AD)
    service.send_to_compliance(MARIA, sid)
    service.give_feedback(CHRIS, service.get(sid).versions[0].findings[0].id, "correct")
    service.decide(CHRIS, sid, APPROVED)


def test_every_action_is_logged_with_who_what_when_version(service, reviewed):
    full_journey(service, reviewed)
    actions = [e.action for e in service.audit_log(reviewed)]
    assert actions == [
        "submitted", "ai_review_completed", "finding_disputed", "sent_to_compliance",
        "decision_returned", "resubmitted", "ai_review_completed", "sent_to_compliance",
        "finding_feedback", "decision_approved",
    ]
    for e in service.audit_log(reviewed):
        assert e.actor and e.role and e.at and e.version_number


def test_ai_events_record_model_and_prompt_version(service, reviewed):
    ai = [e for e in service.audit_log(reviewed) if e.action == "ai_review_completed"]
    assert ai and all(e.ai_model == "fake-model-1" and e.prompt_version for e in ai)
    assert ai[0].actor == "ai-engine" and ai[0].role == "system"


def test_decision_event_records_model_used_for_the_reviewed_version(service, reviewed):
    to_pending(service, reviewed)
    service.decide(CHRIS, reviewed, APPROVED)
    last = service.audit_log(reviewed)[-1]
    assert last.action == "decision_approved" and last.ai_model == "fake-model-1"


def test_orm_blocks_update_and_delete(service, reviewed, session_factory):
    with session_factory() as s:
        e = s.scalars(select(AuditEvent)).first()
        e.action = "tampered"
        with pytest.raises(AuditImmutableError):
            s.commit()
    with session_factory() as s:
        s.delete(s.scalars(select(AuditEvent)).first())
        with pytest.raises(AuditImmutableError):
            s.commit()


def test_database_blocks_raw_sql_tampering(service, reviewed, session_factory):
    with session_factory() as s:
        with pytest.raises(DatabaseError):
            s.execute(text("UPDATE audit_events SET action = 'x'"))
        s.rollback()
        with pytest.raises(DatabaseError):
            s.execute(text("DELETE FROM audit_events"))


def test_hash_chain_verifies_and_detects_tampering(service, reviewed, session_factory):
    full_journey(service, reviewed)
    assert service.verify_audit_chain() == (True, None)
    with session_factory() as s:  # simulate an attacker who bypasses the triggers
        s.execute(text("DROP TRIGGER audit_no_update"))
        s.execute(text("UPDATE audit_events SET actor = 'mallory' WHERE id = 3"))
        s.commit()
    assert service.verify_audit_chain() == (False, 3)
