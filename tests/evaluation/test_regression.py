"""Replays the saved model responses for the sample ads through the current validation
and scoring code. Skips until a real run has recorded responses (eval/results/replay_cache)."""
import dataclasses
import json

import pytest

from config import ANSWER_KEY_PATH, RESULTS_DIR, Settings
from engine.llm import LLMError
from engine.reviewer import Reviewer
from eval.run_eval import load_ads
from eval.scoring import score


@pytest.fixture(scope="module")
def replay_results():
    settings = dataclasses.replace(Settings.load(), llm_provider="replay", llm_model="replay")
    reviewer = Reviewer.from_settings(settings)
    results = {}
    for ad_id, meta, body in load_ads():
        try:
            results[ad_id] = reviewer.review(body, meta.get("channel", ""), meta.get("product", ""))
        except LLMError:
            pytest.skip("No replay cache yet. Run `python eval/run_eval.py` with a real provider first.")
    return results


def test_all_12_ads_have_saved_reviews(replay_results):
    assert len(replay_results) == 12


def test_clean_ad_04_stays_clean(replay_results):
    assert replay_results["AD-04"].findings == []


def test_scores_do_not_regress_from_recorded_baseline(replay_results):
    """No fixed target: the baseline is whatever the last real eval run scored.
    A code change that scores worse on the same saved responses fails here."""
    baseline_path = RESULTS_DIR / "baseline_scores.json"
    if not baseline_path.exists():
        pytest.skip("No baseline yet; run eval/run_eval.py first.")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    key = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    s = score({a: {f.issue_code for f in r.findings} for a, r in replay_results.items()}, key)
    assert s.recall >= baseline["recall"] - 1e-9, f"recall fell from {baseline['recall']:.0%} to {s.recall:.0%}"
    assert s.precision >= baseline["precision"] - 1e-9, f"precision fell from {baseline['precision']:.0%} to {s.precision:.0%}"
