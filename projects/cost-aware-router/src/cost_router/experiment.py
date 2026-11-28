"""Fit routers on train records, score every policy on held-out records, print a table."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .policies import Cascade, CategoryGate, Fixed, Oracle, Outcome, Policy
from .records import Record


@dataclass(frozen=True)
class Score:
    name: str
    accuracy: float
    cost_per_task: float
    escalation_rate: float
    delta_ci: tuple[float, float]  # 95% paired CI of accuracy minus reference accuracy
    detail: str = ""


def paired_delta_ci(a: Sequence[Outcome], b: Sequence[Outcome]) -> tuple[float, float]:
    """95% CI of mean(a.correct) - mean(b.correct), paired per task (normal approximation).

    Pairing matters: both policies see the same tasks, so the per-task difference has far less
    variance than two independent accuracies would suggest.
    """
    diffs = [int(x.correct) - int(y.correct) for x, y in zip(a, b)]
    n = len(diffs)
    if n < 2:
        return (0.0, 0.0)
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    half = 1.96 * math.sqrt(var / n)
    return mean - half, mean + half


def score(policy: Policy, test: Sequence[Record], reference: Policy) -> Score:
    if not test:
        raise ValueError("no test records")
    outs = [policy.route(r) for r in test]
    ref = [reference.route(r) for r in test]
    n = len(outs)
    allowed = getattr(policy, "allowed", None)
    detail = "cheap on: " + (",".join(sorted(allowed)) or "-") if allowed is not None else ""
    return Score(
        policy.name,
        sum(o.correct for o in outs) / n,
        sum(o.cost for o in outs) / n,
        sum(o.escalated for o in outs) / n,
        paired_delta_ci(outs, ref),
        detail,
    )


def build_policies(train: Sequence[Record], max_drop: float) -> list[Policy]:
    small, large, cascade = Fixed("small"), Fixed("large"), Cascade()
    return [
        small,
        large,
        cascade,
        CategoryGate.fit(train, small, large, max_drop, "category"),
        CategoryGate.fit(train, cascade, large, max_drop, "category+cascade"),
        Oracle(),
    ]


def run(train: Sequence[Record], test: Sequence[Record], max_drop: float) -> list[Score]:
    if not train:
        raise ValueError("no train records")
    large = Fixed("large")
    return [score(p, test, large) for p in build_policies(train, max_drop)]


def _large(scores: Sequence[Score]) -> Score:
    return next(s for s in scores if s.name == "always_large")


def _delta(s: Score, large: Score) -> str:
    lo, hi = s.delta_ci
    return f"{(s.accuracy - large.accuracy) * 100:+.1f} [{lo * 100:+.1f},{hi * 100:+.1f}]"


def table(scores: Sequence[Score]) -> str:
    large = _large(scores)
    head = f"{'policy':<18}{'accuracy':>9}{'Δ vs large [95% CI]':>24}{'cost/task':>11}"
    lines = [head + f"{'vs large':>9}{'escal.':>8}  notes"]
    for s in scores:
        lines.append(
            f"{s.name:<18}{s.accuracy * 100:>8.1f}%{_delta(s, large):>24}{s.cost_per_task:>11.3f}"
            f"{s.cost_per_task / large.cost_per_task * 100:>8.0f}%"
            f"{s.escalation_rate * 100:>7.0f}%  {s.detail}".rstrip()
        )
    return "\n".join(lines)


def sweep(
    train: Sequence[Record],
    tests: Sequence[tuple[str, Sequence[Record]]],
    drops: Sequence[float],
    policies: Sequence[str] = ("category", "category+cascade"),
) -> str:
    """For each accuracy budget, the fitted routers' held-out Δ and relative cost per test set."""
    head = f"{'budget':>7}  {'policy':<18}" + "".join(
        f"{name + ' Δ [95% CI]':>24}{'cost':>6}" for name, _ in tests
    )
    lines = [head]
    for drop in drops:
        results = [run(train, t, drop) for _, t in tests]
        for p in policies:
            row = f"{-drop * 100:>6.1f}  {p:<18}"
            for scores in results:
                s, large = next(x for x in scores if x.name == p), _large(scores)
                row += f"{_delta(s, large):>24}{s.cost_per_task / large.cost_per_task:>6.0%}"
            lines.append(row)
    return "\n".join(lines)
