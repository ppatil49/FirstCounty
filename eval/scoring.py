"""Scoring against the answer key: a match is ad_id + issue_code.
Codes in also_acceptable are neutral; anything else unexpected is a false positive."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AdScore:
    ad_id: str
    expected: set[str]
    predicted: set[str]
    acceptable: set[str] = field(default_factory=set)

    @property
    def true_positives(self) -> set[str]:
        return self.predicted & self.expected

    @property
    def false_negatives(self) -> set[str]:
        return self.expected - self.predicted

    @property
    def false_positives(self) -> set[str]:
        return self.predicted - self.expected - self.acceptable

    @property
    def neutral(self) -> set[str]:
        return (self.predicted & self.acceptable) - self.expected


@dataclass
class Score:
    per_ad: list[AdScore]

    @property
    def tp(self) -> int:
        return sum(len(a.true_positives) for a in self.per_ad)

    @property
    def fp(self) -> int:
        return sum(len(a.false_positives) for a in self.per_ad)

    @property
    def fn(self) -> int:
        return sum(len(a.false_negatives) for a in self.per_ad)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def score(predictions: dict[str, set[str]], answer_key: dict) -> Score:
    """predictions: ad_id -> set of issue codes. Only ads in the answer key are scored."""
    per_ad = []
    for ad_id, key in sorted(answer_key["ads"].items()):
        per_ad.append(AdScore(
            ad_id=ad_id,
            expected={f["issue_code"] for f in key.get("expected_findings", [])},
            predicted=set(predictions.get(ad_id, set())),
            acceptable=set(key.get("also_acceptable", [])),
        ))
    return Score(per_ad)
