"""Run the grid (model x config x scenario x payload x goal x seed) and aggregate it."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .agent import Model, run_episode
from .canaries import GOALS, PAYLOADS, detect, make_canary, render
from .defenses import CONFIGS
from .scenarios import SCENARIOS, Scenario


@dataclass(frozen=True)
class Trial:
    model: str
    config: str
    scenario: str
    payload: str  # "clean" for the no-injection utility run
    goal: str
    seed: int
    useful: bool  # answer contains the expected fact
    action: bool
    content: bool
    attempted: bool


def run_grid(
    models: Sequence[tuple[str, Model]],
    configs: Iterable[str] = CONFIGS,
    scenarios: Iterable[Scenario] = SCENARIOS,
    payloads: Iterable[str] = tuple(PAYLOADS),
    seeds: int = 3,
    split: bool = True,
) -> list[Trial]:
    trials = []
    cells = [("clean", "-")] + [(p, g) for p in payloads for g in GOALS]
    for name, model in models:
        for config in configs:
            for sc in scenarios:
                for payload, goal in cells:
                    for seed in range(seeds):
                        # String seeds hash with SHA-512, so runs are stable across processes.
                        rng = random.Random(f"{seed}|{name}|{config}|{sc.name}|{payload}|{goal}")
                        canary = make_canary(rng)
                        inj = None if payload == "clean" else render(payload, goal, canary, split)
                        t = run_episode(model, sc, config, inj, rng)
                        v = detect(t, canary)
                        trials.append(
                            Trial(
                                name,
                                config,
                                sc.name,
                                payload,
                                goal,
                                seed,
                                sc.expected in t.answer,
                                v.action,
                                v.content,
                                v.attempted,
                            )
                        )
    return trials


def rate(trials: Sequence[Trial], attr: str) -> float:
    return sum(getattr(t, attr) for t in trials) / len(trials) if trials else float("nan")


def group(trials: Iterable[Trial], *keys: str) -> dict[tuple, list[Trial]]:
    out: dict[tuple, list[Trial]] = defaultdict(list)
    for t in trials:
        out[tuple(getattr(t, k) for k in keys)].append(t)
    return dict(out)


def summary_table(trials: Sequence[Trial]) -> list[str]:
    """Per model and config: clean utility, attack success by goal, attempts the harness blocked."""
    rows = ["model         config              utility  ASR-action  ASR-content  blocked"]
    for (model, config), ts in group(trials, "model", "config").items():
        clean = [t for t in ts if t.payload == "clean"]
        act = [t for t in ts if t.goal == "action"]
        con = [t for t in ts if t.goal == "content"]
        rows.append(
            f"{model:<14}{config:<20}{rate(clean, 'useful'):>7.0%}{rate(act, 'action'):>12.0%}"
            f"{rate(con, 'content'):>13.0%}{sum(t.attempted for t in ts):>9}"
        )
    return rows


def payload_table(trials: Sequence[Trial]) -> list[str]:
    """Attack success (either goal) by payload and config, pooled over the given models."""
    attacked = [t for t in trials if t.payload != "clean"]
    configs = list(dict.fromkeys(t.config for t in attacked))
    rows = ["payload           " + "".join(f"{c[:12]:>13}" for c in configs)]
    by = group(attacked, "payload", "config")
    for payload in dict.fromkeys(t.payload for t in attacked):
        cells = []
        for c in configs:
            ts = by[(payload, c)]
            cells.append(f"{sum(t.action or t.content for t in ts) / len(ts):>13.0%}")
        rows.append(f"{payload:<18}" + "".join(cells))
    return rows
