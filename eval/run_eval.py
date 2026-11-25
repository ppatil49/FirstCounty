"""Run the engine over all 12 ads, save raw findings, and score AD-01..AD-04.

    python eval/run_eval.py              # uses LLM_PROVIDER from .env
    python eval/run_eval.py --replay     # no API key: uses saved responses
    python eval/run_eval.py --runs 3     # stability check across repeated runs
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from config import ADS_DIR, ANSWER_KEY_PATH, RESULTS_DIR, Settings  # noqa: E402
from engine.reviewer import Reviewer, split_front_matter  # noqa: E402
from eval.scoring import score  # noqa: E402


def load_ads() -> list[tuple[str, dict, str]]:
    ads = []
    for path in sorted(ADS_DIR.glob("AD-*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        ads.append((meta.get("ad_id", path.stem), meta, body))
    return ads


def run_once(reviewer: Reviewer, ads, delay: float = 0.0) -> dict:
    results = {}
    for i, (ad_id, meta, body) in enumerate(ads):
        if i and delay:
            time.sleep(delay)  # stay under free-tier per-minute limits
        print(f"  reviewing {ad_id} ...", flush=True)
        try:
            r = reviewer.review(body, meta.get("channel", "unknown"), meta.get("product", "unknown"))
            results[ad_id] = r.model_dump()
        except Exception as exc:
            results[ad_id] = {"error": str(exc), "findings": []}
            print(f"    ERROR on {ad_id}: {exc}", flush=True)
    return results


def codes(result: dict, confident_only: bool = False) -> set[str]:
    return {f["issue_code"] for f in result.get("findings", [])
            if not (confident_only and f.get("needs_human_review"))}


def report(all_runs: list[dict], key: dict, settings: Settings) -> str:
    first = all_runs[0]
    s_all = score({a: codes(r) for a, r in first.items()}, key)
    s_conf = score({a: codes(r, True) for a, r in first.items()}, key)
    sample = next((r for r in first.values() if "model" in r), {})

    lines = [
        "# Evaluation Report",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · provider `{sample.get('provider', settings.llm_provider)}`"
        f" · model `{sample.get('model', settings.llm_model)}` · prompt `{sample.get('prompt_version', '?')}`",
        "",
        "Scored on AD-01 to AD-04 (the ads with a published answer key). A match is ad_id + issue_code.",
        "",
        "| Metric | All findings | Excluding low-confidence (needs human review) |",
        "| --- | --- | --- |",
        f"| Precision | {s_all.precision:.0%} ({s_all.tp}/{s_all.tp + s_all.fp}) | {s_conf.precision:.0%} ({s_conf.tp}/{s_conf.tp + s_conf.fp}) |",
        f"| Recall | {s_all.recall:.0%} ({s_all.tp}/{s_all.tp + s_all.fn}) | {s_conf.recall:.0%} ({s_conf.tp}/{s_conf.tp + s_conf.fn}) |",
        f"| F1 | {s_all.f1:.2f} | {s_conf.f1:.2f} |",
        "",
        "## Per ad",
        "",
        "| Ad | Expected | Caught | Missed | False positives |",
        "| --- | --- | --- | --- | --- |",
    ]
    for a in s_all.per_ad:
        fmt = lambda xs: ", ".join(sorted(xs)) or "-"  # noqa: E731
        lines.append(f"| {a.ad_id} | {fmt(a.expected)} | {fmt(a.true_positives)} | {fmt(a.false_negatives)} | {fmt(a.false_positives)} |")

    fps = [(a.ad_id, c) for a in s_all.per_ad for c in sorted(a.false_positives)]
    if fps:
        lines += ["", "### False positives explained by the engine", ""]
        for ad_id, c in fps:
            f = next(f for f in first[ad_id]["findings"] if f["issue_code"] == c)
            lines.append(f"- **{ad_id} {c}** (confidence {f['confidence']}): {f['explanation']}")

    lines += ["", "## Findings on all 12 ads", "", "| Ad | Findings (code, severity, confidence) |", "| --- | --- |"]
    for ad_id, r in first.items():
        if "error" in r:
            lines.append(f"| {ad_id} | ERROR: {r['error']} |")
            continue
        items = [f"{f['issue_code']} ({f['severity']}, {f['confidence']}{', review' if f['needs_human_review'] else ''})"
                 for f in r["findings"]]
        lines.append(f"| {ad_id} | {'; '.join(items) or 'clean'} |")

    if len(all_runs) > 1:
        lines += ["", f"## Stability across {len(all_runs)} runs", "",
                  "Failed calls (e.g. rate limits) are counted separately and excluded from the comparison.", "",
                  "| Ad | Successful runs | Codes that changed between successful runs | Errors |",
                  "| --- | --- | --- | --- |"]
        for ad_id in first:
            ok = [run[ad_id] for run in all_runs if "error" not in run.get(ad_id, {"error": 1})]
            errors = len(all_runs) - len(ok)
            seen = Counter(c for r in ok for c in codes(r))
            unstable = sorted(c for c, n in seen.items() if n != len(ok))
            lines.append(f"| {ad_id} | {len(ok)}/{len(all_runs)} | {', '.join(unstable) or 'stable'} | {errors or '-'} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true", help="use saved responses; no API key needed")
    ap.add_argument("--runs", type=int, default=1, help="repeat runs to check stability")
    ap.add_argument("--delay", type=float, default=0.0, help="seconds to wait between calls (free-tier rate limits)")
    ap.add_argument("--out", default=None,
                    help="write results to eval/results/<OUT>/ (own replay cache, no baseline), e.g. --out ollama")
    args = ap.parse_args()

    out_dir = RESULTS_DIR / args.out if args.out else RESULTS_DIR
    settings = Settings.load()
    if args.out:  # keep this provider's recorded responses away from the main replay cache
        settings = dataclasses.replace(settings, replay_dir=out_dir / "replay_cache")
    if args.replay:
        settings = dataclasses.replace(settings, llm_provider="replay", llm_model="replay")
    reviewer = Reviewer.from_settings(settings)
    key = json.loads(ANSWER_KEY_PATH.read_text(encoding="utf-8"))
    ads = load_ads()

    all_runs = []
    for i in range(args.runs):
        print(f"Run {i + 1}/{args.runs} with provider '{settings.llm_provider}' model '{settings.llm_model}'")
        all_runs.append(run_once(reviewer, ads, 0.0 if args.replay else args.delay))

    out_dir.mkdir(parents=True, exist_ok=True)
    failed = sorted({a for run in all_runs for a, r in run.items() if "error" in r})
    # A run with errors never overwrites good results: it is saved with a ".partial" suffix instead.
    suffix = ".partial" if failed else ""
    raw = [{"ad_id": ad_id, **result} for ad_id, result in all_runs[0].items()]
    (out_dir / f"findings_all_12{suffix}.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    if len(all_runs) > 1:
        every = [[{"ad_id": a, **r} for a, r in run.items()] for run in all_runs]
        (out_dir / f"findings_all_runs{suffix}.json").write_text(json.dumps(every, indent=2, ensure_ascii=False), encoding="utf-8")
    text = report(all_runs, key, settings)
    (out_dir / f"eval_report{suffix}.md").write_text(text, encoding="utf-8")
    if not args.replay and not args.out and not failed:
        # A clean real run on the main provider sets the regression baseline used by tests/evaluation.
        s = score({a: codes(r) for a, r in all_runs[0].items()}, key)
        (RESULTS_DIR / "baseline_scores.json").write_text(
            json.dumps({"precision": s.precision, "recall": s.recall}, indent=2), encoding="utf-8")
    print()
    print(text)
    if failed:
        print(f"WARNING: {len(failed)} ad(s) failed ({', '.join(failed)}). Results saved with '.partial' "
              f"in {out_dir}; existing results were not overwritten.")
        return 1
    print(f"Saved {out_dir / 'findings_all_12.json'} and {out_dir / 'eval_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
