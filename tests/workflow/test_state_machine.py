import pytest

from tests.helpers import BAD_AD, CHRIS, FIXED_AD, MARIA, to_pending
from workflow.service import (
    AI_REVIEWED, APPROVED, PENDING_COMPLIANCE, REJECTED, RETURNED, SUBMITTED, InvalidTransition,
)


def test_submission_gets_id_and_is_reviewed_automatically(service, reviewed):
    sub = service.get(reviewed)
    assert sub.id == "SUB-0001"
    assert sub.status == AI_REVIEWED
    assert [e.to_status for e in service.audit_log(reviewed)][:2] == [SUBMITTED, AI_REVIEWED]


def test_ids_are_sequential(service):
    a = service.submit(MARIA, "a", "web", "deposit", "x")
    b = service.submit(MARIA, "b", "web", "deposit", "y")
    assert (a, b) == ("SUB-0001", "SUB-0002")


def test_ai_failure_keeps_status_submitted_and_can_be_retried(service, fake_llm):
    fake_llm.fail = True
    sid = service.submit(MARIA, "t", "web", "deposit", BAD_AD)
    sub = service.get(sid)
    assert sub.status == SUBMITTED and "fake outage" in sub.versions[-1].ai_error
    fake_llm.fail = False
    service.retry_ai_review(MARIA, sid)
    assert service.get(sid).status == AI_REVIEWED


@pytest.mark.parametrize("decision,comment", [(APPROVED, None), (RETURNED, "fix it"), (REJECTED, "cannot run")])
def test_compliance_decisions_set_status(service, reviewed, decision, comment):
    to_pending(service, reviewed)
    assert service.get(reviewed).status == PENDING_COMPLIANCE
    service.decide(CHRIS, reviewed, decision, comment)
    assert service.get(reviewed).status == decision


def test_returned_piece_goes_back_to_marketing_via_resubmit(service, reviewed):
    to_pending(service, reviewed)
    service.decide(CHRIS, reviewed, RETURNED, "Add the APY disclosures")
    service.resubmit(MARIA, reviewed, FIXED_AD)
    sub = service.get(reviewed)
    assert sub.status == AI_REVIEWED and len(sub.versions) == 2


@pytest.mark.parametrize("final", [APPROVED, REJECTED])
def test_final_statuses_allow_no_further_changes(service, reviewed, final):
    to_pending(service, reviewed)
    service.decide(CHRIS, reviewed, final, "done")
    with pytest.raises(InvalidTransition):
        service.resubmit(MARIA, reviewed, FIXED_AD)
    with pytest.raises(InvalidTransition):
        service.decide(CHRIS, reviewed, APPROVED)


def test_cannot_decide_before_pending(service, reviewed):
    with pytest.raises(InvalidTransition):
        service.decide(CHRIS, reviewed, APPROVED)


def test_cannot_respond_while_pending(service, reviewed):
    fid = service.get(reviewed).versions[-1].findings[0].id
    to_pending(service, reviewed)
    with pytest.raises(InvalidTransition):
        service.respond(MARIA, fid, "accept")


def test_cannot_answer_findings_of_an_old_version(service, reviewed):
    old = service.get(reviewed).versions[-1].findings[0].id
    service.resubmit(MARIA, reviewed, BAD_AD + " (v2)")
    with pytest.raises(InvalidTransition):
        service.respond(MARIA, old, "accept")
