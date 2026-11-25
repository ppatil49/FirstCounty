import pytest

from engine.prompts import PROMPT_VERSION
from engine.reviewer import Reviewer, split_front_matter
from engine.validate import OutputParseError
from tests.fakes.fake_llm import FakeLLM, finding

SAMPLE = "---\nad_id: AD-99\nchannel: Website\nproduct: Deposit\nsynthetic: true\n---\n\n# Hello\nEarn 4.25%!\n"


def test_front_matter_split():
    meta, body = split_front_matter(SAMPLE)
    assert meta["ad_id"] == "AD-99" and meta["channel"] == "Website"
    assert body.strip().startswith("# Hello")


def test_ad_id_is_never_sent_to_the_model():
    llm = FakeLLM()
    meta, body = split_front_matter(SAMPLE)
    Reviewer(llm).review(body, meta["channel"], meta["product"])
    assert "AD-99" not in llm.calls[0]["user"] and "AD-99" not in llm.calls[0]["system"]


def test_review_records_model_and_prompt_version():
    llm = FakeLLM(lambda _p: [finding("REGDD_RATE_NOT_APY", "Earn 4.25%!")])
    r = Reviewer(llm).review("Earn 4.25%!", "web", "deposit")
    assert r.model == "fake-model-1" and r.provider == "fake" and r.prompt_version == PROMPT_VERSION
    assert [f.issue_code for f in r.findings] == ["REGDD_RATE_NOT_APY"]


def test_clean_piece_returns_no_findings():
    assert Reviewer(FakeLLM()).review("Member FDIC", "web", "deposit").findings == []


def test_unparseable_model_output_raises():
    with pytest.raises(OutputParseError):
        Reviewer(FakeLLM(lambda _p: "I cannot help with that")).review("x", "web", "deposit")
