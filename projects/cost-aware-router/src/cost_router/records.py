"""Per-task eval records: what the router learns from, and a simulator that produces them.

A record says, for one task, whether each model got it right, what each call cost, and whether two
samples from the small model agreed. That is all the router may look at; difficulty is hidden.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

# Hidden mean difficulty per category, in [0, 1]. Only the simulator sees these.
CATEGORIES: dict[str, float] = {
    "extract": 0.10,
    "classify": 0.20,
    "summarize": 0.30,
    "code": 0.55,
    "math": 0.65,
}
LARGE_COST_RATIO = 15.0  # assumed price ratio large/small per token; not a quoted price


@dataclass(frozen=True)
class Record:
    task_id: str
    category: str
    small_correct: bool
    large_correct: bool
    small_agree: bool  # two small-model samples gave the same answer
    small_cost: float  # cost of ONE small call
    large_cost: float


def _clip(x: float) -> float:
    return min(1.0, max(0.0, x))


def simulate(
    n: int,
    seed: int,
    drift: dict[str, float] | None = None,
    mix: dict[str, float] | None = None,
) -> list[Record]:
    """Draw `n` tasks. `drift` adds to a category's difficulty; `mix` reweights categories.

    Model: both models are near-perfect on easy tasks; past that, small accuracy falls steeply
    with difficulty and large accuracy gently. The small model agrees with itself 90% of the time
    when right and 35% when wrong (it is often confidently wrong), so agreement is a useful but
    leaky correctness signal.
    """
    rng = random.Random(seed)
    drift = drift or {}
    names = list(CATEGORIES)
    weights = [(mix or {}).get(c, 1.0) for c in names]
    out = []
    for i in range(n):
        cat = rng.choices(names, weights)[0]
        d = _clip(rng.gauss(CATEGORIES[cat] + drift.get(cat, 0.0), 0.15))
        hard = max(0.0, d - 0.15)  # below 0.15 both models are near their ceiling
        small_ok = rng.random() < _clip(0.97 - 1.0 * hard)
        large_ok = rng.random() < _clip(0.98 - 0.3 * hard)
        agree = rng.random() < (0.90 if small_ok else 0.35)
        tokens = max(50.0, rng.gauss(400 + 800 * d, 100))
        small_cost = round(tokens / 1000, 6)  # 1 cost unit per 1K tokens on the small model
        large_cost = round(small_cost * LARGE_COST_RATIO, 6)
        out.append(Record(f"t{seed}-{i}", cat, small_ok, large_ok, agree, small_cost, large_cost))
    return out


def split(records: Iterable[Record], test_fraction: float = 0.5) -> tuple[list[Record], ...]:
    """Stable train/test split by hashing task_id, so the same record always lands on one side."""
    train, test = [], []
    for r in records:
        h = int(hashlib.sha256(r.task_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        (test if h < test_fraction else train).append(r)
    return train, test


def dump_jsonl(records: Iterable[Record], path: Path) -> None:
    path.write_text("".join(json.dumps(asdict(r)) + "\n" for r in records))


def load_jsonl(path: Path) -> list[Record]:
    out = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            row = json.loads(line)
            try:
                out.append(Record(**row))
            except TypeError as e:
                raise ValueError(f"{path}:{n}: bad record: {e}") from None
    return out
