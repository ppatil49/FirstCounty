import pytest

from eval.scoring import score

KEY = {"ads": {
    "AD-01": {"expected_findings": [{"issue_code": "A"}, {"issue_code": "B"}, {"issue_code": "C"}],
              "also_acceptable": ["N"]},
    "AD-02": {"expected_findings": [{"issue_code": "D"}]},
    "AD-03": {"expected_findings": []},
}}


def test_perfect_predictions():
    s = score({"AD-01": {"A", "B", "C"}, "AD-02": {"D"}, "AD-03": set()}, KEY)
    assert (s.precision, s.recall, s.f1) == (1.0, 1.0, 1.0)


def test_misses_false_positives_and_neutral_codes():
    s = score({"AD-01": {"A", "B", "N", "X"}, "AD-02": set(), "AD-03": {"Y"}}, KEY)
    assert (s.tp, s.fp, s.fn) == (2, 2, 2)  # N is neutral; X and Y are false positives
    assert s.precision == pytest.approx(0.5) and s.recall == pytest.approx(0.5)
    ad1 = s.per_ad[0]
    assert ad1.neutral == {"N"} and ad1.false_negatives == {"C"}


def test_ads_outside_the_key_are_ignored():
    s = score({"AD-01": {"A", "B", "C"}, "AD-02": {"D"}, "AD-09": {"Z"}}, KEY)
    assert s.fp == 0


def test_no_predictions_on_clean_key_gives_full_precision():
    s = score({}, {"ads": {"AD-04": {"expected_findings": []}}})
    assert (s.precision, s.recall) == (1.0, 1.0)
