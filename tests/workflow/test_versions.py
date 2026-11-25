import pytest

from tests.helpers import BAD_AD, FIXED_AD, MARIA
from workflow.service import ValidationFailed


def test_resubmit_creates_new_version_and_keeps_old(service, reviewed):
    n = service.resubmit(MARIA, reviewed, FIXED_AD)
    sub = service.get(reviewed)
    assert n == 2
    assert [v.number for v in sub.versions] == [1, 2]
    assert sub.versions[0].content == BAD_AD and sub.versions[1].content == FIXED_AD


def test_each_version_gets_its_own_ai_review(service, reviewed, fake_llm):
    service.resubmit(MARIA, reviewed, FIXED_AD)
    v1, v2 = service.get(reviewed).versions
    assert len(fake_llm.calls) == 2
    assert [f.issue_code for f in v1.findings] == ["REGDD_RATE_NOT_APY", "UDAAP_MISLEADING"]
    assert v2.findings == [] and v2.ai_model == "fake-model-1" and v2.prompt_version


def test_diff_shows_changes(service, reviewed):
    service.resubmit(MARIA, reviewed, FIXED_AD)
    d = service.diff(reviewed, 1, 2)
    assert "-12-Month CD Special. Earn 4.25%!" in d and "+12-Month CD Special. Earn 4.25% APY." in d


def test_identical_resubmission_rejected(service, reviewed):
    with pytest.raises(ValidationFailed):
        service.resubmit(MARIA, reviewed, BAD_AD)
