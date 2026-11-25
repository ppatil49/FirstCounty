"""Full path an examiner would want to reconstruct: submit -> AI flags -> dispute ->
Compliance returns -> revise -> AI clears -> Compliance approves, with feedback stored."""
from tests.helpers import BAD_AD, CHRIS, FIXED_AD, MARIA, finding_ids
from workflow.service import AI_REVIEWED, APPROVED, PENDING_COMPLIANCE, RETURNED


def test_full_journey_and_reconstruction(service):
    sid = service.submit(MARIA, "Holiday CD postcard", "mailer", "deposit", BAD_AD)
    assert service.get(sid).status == AI_REVIEWED

    high = finding_ids(service, sid, "high")[0]
    service.respond(MARIA, high, "dispute", "APY is printed on the reverse")
    service.send_to_compliance(MARIA, sid)
    assert service.get(sid).status == PENDING_COMPLIANCE

    # Compliance agrees with the AI, not the dispute, and sends it back
    service.give_feedback(CHRIS, high, "correct", "Reverse side was not submitted")
    service.decide(CHRIS, sid, RETURNED, "Show APY on this side and add Member FDIC")
    assert service.get(sid).status == RETURNED

    service.resubmit(MARIA, sid, FIXED_AD)
    assert service.gate_blockers(sid) == []
    service.send_to_compliance(MARIA, sid)
    service.decide(CHRIS, sid, APPROVED)

    sub = service.get(sid)
    assert sub.status == APPROVED
    assert [d.decision for d in sub.decisions] == [RETURNED, APPROVED]
    assert sub.versions[0].findings[0].latest_feedback.verdict == "correct"
    assert sub.versions[0].findings[0].latest_response.reason == "APY is printed on the reverse"

    # Reconstruct the story purely from the audit log
    story = [(e.actor, e.action, e.version_number, e.to_status) for e in service.audit_log(sid)]
    assert story == [
        ("maria", "submitted", 1, "SUBMITTED"),
        ("ai-engine", "ai_review_completed", 1, "AI_REVIEWED"),
        ("maria", "finding_disputed", 1, None),
        ("maria", "sent_to_compliance", 1, "PENDING_COMPLIANCE"),
        ("chris", "finding_feedback", 1, None),
        ("chris", "decision_returned", 1, "RETURNED"),
        ("maria", "resubmitted", 2, "SUBMITTED"),
        ("ai-engine", "ai_review_completed", 2, "AI_REVIEWED"),
        ("maria", "sent_to_compliance", 2, "PENDING_COMPLIANCE"),
        ("chris", "decision_approved", 2, "APPROVED"),
    ]
    assert service.verify_audit_chain() == (True, None)
