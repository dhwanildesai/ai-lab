"""Paired measurement: every task is its own control, and the task is the unit of resampling."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import NamedTuple

from .mutations import MUTATIONS, mutate
from .registry import Task, Tool
from .selectors import Selector


class Effect(NamedTuple):
    mutation: str
    accuracy: float  # mean over seeds and tasks
    delta: float  # accuracy minus baseline
    low: float  # 95% bootstrap interval for delta
    high: float
    p_holm: float  # sign-flip test, Holm-corrected across mutations
    flips: float  # fraction of (task, seed) pairs whose chosen tool changed, right or wrong


class Hijack(NamedTuple):
    mutation: str
    own_before: float  # recall of the edited tool on its own tasks
    own_after: float
    stolen: float  # share of other tools' previously correct tasks that moved to the edited tool


def choices(selector: Selector, tools: Sequence[Tool], tasks: Sequence[Task]) -> list[str | None]:
    return [selector.select(t.query, tools) for t in tasks]


def accuracy(selector: Selector, tools: Sequence[Tool], tasks: Sequence[Task]) -> float:
    picked = choices(selector, tools, tasks)
    return sum(p == t.expected for p, t in zip(picked, tasks)) / len(tasks)


def bootstrap_ci(values: Sequence[float], rounds: int = 2000) -> tuple[float, float]:
    rng = random.Random("bootstrap")
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(rounds))
    return means[int(0.025 * rounds)], means[int(0.975 * rounds) - 1]


def sign_flip_p(values: Sequence[float], rounds: int = 2000) -> float:
    """Two-sided Monte Carlo test that per-task deltas are symmetric around zero."""
    rng = random.Random("sign-flip")
    observed = abs(sum(values))
    hits = 0
    for _ in range(rounds):
        total = sum(v if rng.random() < 0.5 else -v for v in values)
        hits += abs(total) >= observed - 1e-12
    return (hits + 1) / (rounds + 1)


def holm(p_values: dict[str, float]) -> dict[str, float]:
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, name in enumerate(sorted(p_values, key=lambda k: p_values[k])):
        running = max(running, min(1.0, p_values[name] * (len(p_values) - rank)))
        adjusted[name] = running
    return adjusted


def measure(
    selector: Selector, tools: Sequence[Tool], tasks: Sequence[Task], seeds: int = 20
) -> list[Effect]:
    """Mutate all tools at once. Per-task deltas are averaged over seeds before any statistics:
    seeds reuse the same tasks, so counting them as samples would fake precision."""
    base = choices(selector, tools, tasks)
    base_ok = [p == t.expected for p, t in zip(base, tasks)]
    base_acc = sum(base_ok) / len(tasks)
    deltas: dict[str, list[float]] = {}
    flips: dict[str, float] = {}
    for name in MUTATIONS:
        gained = [0] * len(tasks)
        changed = 0
        for seed in range(seeds):
            picked = choices(selector, mutate(tools, name, seed), tasks)
            for i, (pick, task) in enumerate(zip(picked, tasks)):
                gained[i] += (pick == task.expected) - base_ok[i]
                changed += pick != base[i]
        deltas[name] = [g / seeds for g in gained]
        flips[name] = changed / (seeds * len(tasks))
    p_holm = holm({n: sign_flip_p(d) for n, d in deltas.items() if n != "identity"})
    effects = []
    for name, values in deltas.items():
        delta = sum(values) / len(values)
        low, high = bootstrap_ci(values)
        effects.append(
            Effect(name, base_acc + delta, delta, low, high, p_holm.get(name, 1.0), flips[name])
        )
    return effects


def hijack(
    selector: Selector,
    tools: Sequence[Tool],
    tasks: Sequence[Task],
    name: str,
    seeds: int = 20,
) -> Hijack:
    """Edit one tool at a time, as a single third-party server could; average over edited tools."""
    base = choices(selector, tools, tasks)
    own_total = own_before = own_after = at_risk = stolen = 0
    for tool in tools:
        for seed in range(seeds):
            picked = choices(selector, mutate(tools, name, seed, only=tool.name), tasks)
            for before, after, task in zip(base, picked, tasks):
                if task.expected == tool.name:
                    own_total += 1
                    own_before += before == tool.name
                    own_after += after == tool.name
                elif before == task.expected:
                    at_risk += 1
                    stolen += after == tool.name
    if not own_total or not at_risk:
        raise ValueError("need tasks for the tools and at least one correct baseline choice")
    return Hijack(name, own_before / own_total, own_after / own_total, stolen / at_risk)
