import pytest

from tests.helpers import BAD_AD, CHRIS, FIXED_AD, MARIA, finding_ids, to_pending
from workflow.service import APPROVED, REJECTED, RETURNED, PermissionDenied


@pytest.mark.parametrize("decision", [APPROVED, RETURNED, REJECTED])
def test_marketing_cannot_decide(service, reviewed, decision):
    to_pending(service, reviewed)
    with pytest.raises(PermissionDenied):
        service.decide(MARIA, reviewed, decision, "self-approve")


def test_marketing_cannot_rate_findings(service, reviewed):
    to_pending(service, reviewed)
    with pytest.raises(PermissionDenied):
        service.give_feedback(MARIA, finding_ids(service, reviewed)[0], "incorrect")


def test_compliance_cannot_edit_submit_or_respond(service, reviewed):
    with pytest.raises(PermissionDenied):
        service.submit(CHRIS, "t", "web", "deposit", BAD_AD)
    with pytest.raises(PermissionDenied):
        service.resubmit(CHRIS, reviewed, FIXED_AD)
    with pytest.raises(PermissionDenied):
        service.respond(CHRIS, finding_ids(service, reviewed)[0], "accept")
    with pytest.raises(PermissionDenied):
        service.send_to_compliance(CHRIS, reviewed)


def test_denied_attempt_changes_nothing(service, reviewed):
    to_pending(service, reviewed)
    before = len(service.audit_log(reviewed))
    with pytest.raises(PermissionDenied):
        service.decide(MARIA, reviewed, APPROVED)
    assert len(service.audit_log(reviewed)) == before
