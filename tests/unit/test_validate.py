import pytest

from engine.knowledge import taxonomy
from engine.validate import OutputParseError, merge_duplicates, parse_json, quote_in_text, validate_findings
from tests.fakes.fake_llm import finding

AD = "# LOCK IN A GREAT RATE\n\n## 12-Month CD Special — Earn **4.25%**!\n\n*Limited time offer.*"


def run(items, threshold=0.6):
    return validate_findings(items, AD, threshold)


def test_unknown_issue_code_is_dropped():
    kept, dropped = run([finding("MADE_UP_CODE", None)])
    assert kept == []
    assert "unknown issue_code" in dropped[0]["reason"]


def test_every_kept_finding_has_all_seven_fields_and_taxonomy_citation():
    kept, _ = run([finding("REGDD_RATE_NOT_APY", "Earn 4.25%!")])
    f = kept[0]
    for field in ["issue_code", "regulation", "offending_text", "explanation", "suggested_fix", "severity", "confidence"]:
        assert field in f.model_dump()
    assert f.regulation == taxonomy()["REGDD_RATE_NOT_APY"]["regulation"]  # never the model's citation


def test_quote_matches_despite_markdown_and_spacing():
    assert quote_in_text("Earn 4.25%!", AD)
    assert quote_in_text("limited time offer", AD)


def test_invented_quote_is_nulled_and_confidence_lowered():
    kept, _ = run([finding("UDAAP_MISLEADING", "Best rates in the world", confidence=0.9)])
    f = kept[0]
    assert f.offending_text is None
    assert f.confidence == pytest.approx(0.7)
    assert any("not found" in n for n in f.validation_notes)


def test_null_like_strings_become_null():
    kept, _ = run([finding("FDIC_MISSING_STATEMENT", "null")])
    assert kept[0].offending_text is None
    assert kept[0].validation_notes == []


def test_duplicate_codes_merge_into_one_keeping_strongest():
    kept, _ = run([
        finding("REGDD_MISSING_APY_TERMS", None, severity="medium", confidence=0.6, explanation="No as-of date."),
        finding("REGDD_MISSING_APY_TERMS", None, severity="high", confidence=0.9, explanation="No minimum balance."),
    ])
    assert len(kept) == 1
    f = kept[0]
    assert (f.severity, f.confidence) == ("high", 0.9)
    assert "No as-of date." in f.explanation and "No minimum balance." in f.explanation


def test_low_confidence_is_flagged_for_human_review():
    kept, _ = run([finding("UDAAP_MISLEADING", None, confidence=0.4),
                   finding("FDIC_MISSING_STATEMENT", None, confidence=0.95)])
    flags = {f.issue_code: f.needs_human_review for f in kept}
    assert flags == {"UDAAP_MISLEADING": True, "FDIC_MISSING_STATEMENT": False}


def test_bad_severity_and_confidence_are_normalized():
    item = finding("FDIC_MISSING_STATEMENT", None)
    item.update(severity="CRITICAL", confidence="very")
    f = run([item])[0][0]
    assert (f.severity, f.confidence) == ("medium", 0.5)


def test_results_sorted_high_first():
    kept, _ = run([finding("UDAAP_MISLEADING", None, severity="low"),
                   finding("FDIC_MISSING_STATEMENT", None, severity="high")])
    assert [f.severity for f in kept] == ["high", "low"]


def test_parse_json_handles_fences_and_rejects_garbage():
    assert parse_json('```json\n{"findings": []}\n```') == {"findings": []}
    assert parse_json('Sure! {"findings": []} Hope that helps') == {"findings": []}
    with pytest.raises(OutputParseError):
        parse_json("no json here")


def test_merge_duplicates_on_empty_list():
    assert merge_duplicates([]) == []
