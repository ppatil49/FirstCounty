import pytest

from tests.helpers import CHRIS, MARIA, finding_ids, to_pending
from workflow.service import APPROVED, REJECTED, RETURNED, ValidationFailed


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_dispute_requires_reason(service, reviewed, reason):
    with pytest.raises(ValidationFailed):
        service.respond(MARIA, finding_ids(service, reviewed)[0], "dispute", reason)


def test_accept_needs_no_reason(service, reviewed):
    service.respond(MARIA, finding_ids(service, reviewed)[0], "accept")


@pytest.mark.parametrize("decision", [RETURNED, REJECTED])
@pytest.mark.parametrize("comment", [None, "", "  "])
def test_return_and_reject_require_comment(service, reviewed, decision, comment):
    to_pending(service, reviewed)
    with pytest.raises(ValidationFailed):
        service.decide(CHRIS, reviewed, decision, comment)


def test_approve_comment_is_optional_and_stored(service, reviewed):
    to_pending(service, reviewed)
    service.decide(CHRIS, reviewed, APPROVED, "Use only until Dec 31")
    assert service.get(reviewed).decisions[-1].comment == "Use only until Dec 31"


def test_submit_validates_inputs(service):
    with pytest.raises(ValidationFailed):
        service.submit(MARIA, "", "web", "deposit", "x")
    with pytest.raises(ValidationFailed):
        service.submit(MARIA, "t", "billboard", "deposit", "x")
    with pytest.raises(ValidationFailed):
        service.submit(MARIA, "t", "web", "crypto", "x")
