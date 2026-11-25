"""A run with errors (e.g. rate limits) must never overwrite good saved results."""
import sys

import eval.run_eval as run_eval
from engine.reviewer import Reviewer
from tests.fakes.fake_llm import FakeLLM


def run_main(monkeypatch, tmp_path, llm, *args):
    monkeypatch.setattr(run_eval, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(Reviewer, "from_settings", classmethod(lambda cls, s=None: cls(llm)))
    monkeypatch.setattr(sys, "argv", ["run_eval.py", *args])
    return run_eval.main()


def test_failed_run_keeps_existing_results(monkeypatch, tmp_path):
    (tmp_path / "findings_all_12.json").write_text("GOOD", encoding="utf-8")
    (tmp_path / "eval_report.md").write_text("GOOD", encoding="utf-8")
    (tmp_path / "baseline_scores.json").write_text("GOOD", encoding="utf-8")

    assert run_main(monkeypatch, tmp_path, FakeLLM(fail=True)) == 1

    for name in ["findings_all_12.json", "eval_report.md", "baseline_scores.json"]:
        assert (tmp_path / name).read_text(encoding="utf-8") == "GOOD"
    assert (tmp_path / "findings_all_12.partial.json").exists()
    assert (tmp_path / "eval_report.partial.md").exists()


def test_clean_run_writes_results_and_baseline(monkeypatch, tmp_path):
    assert run_main(monkeypatch, tmp_path, FakeLLM()) == 0
    assert (tmp_path / "findings_all_12.json").exists()
    assert (tmp_path / "baseline_scores.json").exists()


def test_out_dir_is_separate_and_sets_no_baseline(monkeypatch, tmp_path):
    assert run_main(monkeypatch, tmp_path, FakeLLM(), "--out", "ollama") == 0
    assert (tmp_path / "ollama" / "findings_all_12.json").exists()
    assert not (tmp_path / "findings_all_12.json").exists()
    assert not (tmp_path / "baseline_scores.json").exists()
