"""Routing policies. Each maps a record to what would have happened under that policy.

Because every record carries both models' outcomes, any policy can be scored offline against the
same eval log, with no extra model calls (counterfactual replay).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from .records import Record


@dataclass(frozen=True)
class Outcome:
    correct: bool
    cost: float
    escalated: bool = False


class Policy:
    name = "policy"

    def route(self, r: Record) -> Outcome:
        raise NotImplementedError


class Fixed(Policy):
    def __init__(self, tier: str) -> None:
        if tier not in ("small", "large"):
            raise ValueError(f"tier must be small or large, got {tier!r}")
        self.tier = tier
        self.name = f"always_{tier}"

    def route(self, r: Record) -> Outcome:
        if self.tier == "small":
            return Outcome(r.small_correct, r.small_cost)
        return Outcome(r.large_correct, r.large_cost)


class Oracle(Policy):
    """Knows the answer in advance: small when small is right (or both are wrong), else large."""

    name = "oracle"

    def route(self, r: Record) -> Outcome:
        if r.small_correct or not r.large_correct:
            return Outcome(r.small_correct, r.small_cost)
        return Outcome(True, r.large_cost)


class Cascade(Policy):
    """Sample the small model twice; accept if the samples agree, else escalate to large.

    Pays 2 small calls on every task, and small + large on escalations.
    """

    name = "cascade"

    def route(self, r: Record) -> Outcome:
        cost = 2 * r.small_cost
        if r.small_agree:
            return Outcome(r.small_correct, cost)
        return Outcome(r.large_correct, cost + r.large_cost, escalated=True)


class CategoryGate(Policy):
    """Use `cheap` for the categories in `allowed`, `expensive` for everything else."""

    def __init__(self, cheap: Policy, expensive: Policy, allowed: frozenset[str], name: str):
        self.cheap, self.expensive, self.allowed, self.name = cheap, expensive, allowed, name

    def route(self, r: Record) -> Outcome:
        return (self.cheap if r.category in self.allowed else self.expensive).route(r)

    @classmethod
    def fit(
        cls,
        train: Sequence[Record],
        cheap: Policy,
        expensive: Policy,
        max_drop: float,
        name: str,
    ) -> CategoryGate:
        """Greedily allow categories, cheapest accuracy-loss-per-cost-saved first, while train
        accuracy stays within `max_drop` (absolute, e.g. 0.01) of `expensive` alone."""
        by_cat: dict[str, list[Record]] = defaultdict(list)
        for r in train:
            by_cat[r.category].append(r)
        loss: dict[str, int] = {}  # extra wrong answers if this category goes cheap
        saved: dict[str, float] = {}
        for cat, rs in by_cat.items():
            c, e = [cheap.route(r) for r in rs], [expensive.route(r) for r in rs]
            loss[cat] = sum(x.correct for x in e) - sum(x.correct for x in c)
            saved[cat] = sum(x.cost for x in e) - sum(x.cost for x in c)
        budget = max_drop * len(train)  # wrong answers we may add over `expensive`
        allowed: list[str] = []
        spent = 0
        for cat in sorted(by_cat, key=lambda k: (loss[k] / max(saved[k], 1e-12), k)):
            if saved[cat] > 0 and spent + loss[cat] <= budget:
                allowed.append(cat)
                spent += loss[cat]
        return cls(cheap, expensive, frozenset(allowed), name)
