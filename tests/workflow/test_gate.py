import pytest

from tests.helpers import FIXED_AD, MARIA, finding_ids
from workflow.service import PENDING_COMPLIANCE, GateBlocked


def test_blocked_while_high_finding_unanswered(service, reviewed):
    assert service.gate_blockers(reviewed) == ["REGDD_RATE_NOT_APY: high finding has no response"]
    with pytest.raises(GateBlocked):
        service.send_to_compliance(MARIA, reviewed)


def test_accepted_high_finding_blocks_until_fixed(service, reviewed):
    service.respond(MARIA, finding_ids(service, reviewed, "high")[0], "accept")
    assert "accepted but not yet fixed" in service.gate_blockers(reviewed)[0]


def test_disputed_high_finding_passes(service, reviewed):
    service.respond(MARIA, finding_ids(service, reviewed, "high")[0], "dispute", "APY is on the back")
    assert service.gate_blockers(reviewed) == []
    service.send_to_compliance(MARIA, reviewed)
    assert service.get(reviewed).status == PENDING_COMPLIANCE


def test_fixed_by_resubmission_passes(service, reviewed):
    service.respond(MARIA, finding_ids(service, reviewed, "high")[0], "accept")
    service.resubmit(MARIA, reviewed, FIXED_AD)  # fake AI now returns no findings
    assert service.gate_blockers(reviewed) == []


def test_low_and_medium_findings_never_block(service, reviewed):
    service.respond(MARIA, finding_ids(service, reviewed, "high")[0], "dispute", "reason")
    low = finding_ids(service, reviewed, "low")
    assert low, "fixture should include a low finding"
    assert service.gate_blockers(reviewed) == []  # low finding left unanswered


def test_latest_response_wins(service, reviewed):
    fid = finding_ids(service, reviewed, "high")[0]
    service.respond(MARIA, fid, "dispute", "reason")
    service.respond(MARIA, fid, "accept")
    assert service.gate_blockers(reviewed)
