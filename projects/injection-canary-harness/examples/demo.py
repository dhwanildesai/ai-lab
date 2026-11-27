"""Print the result tables. `--cmd "..."` scores an external (e.g. live) agent instead."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # run without installing

from canary_harness.experiment import payload_table, rate, run_grid, summary_table
from canary_harness.models import SIMULATED, CommandModel
from canary_harness.scenarios import SCENARIOS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--cmd", help="command: request JSON on stdin, reply JSON on stdout")
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be at least 1")

    if args.cmd:
        model = CommandModel(args.cmd)
        models = [(model.name, model)]
        label = "external"
    else:
        models = [(m.name, m) for m in SIMULATED]
        label = "simulated"
    trials = run_grid(models, seeds=args.seeds)
    print(f"{len(trials)} episodes ({label}), {len(SCENARIOS)} scenarios, {args.seeds} seeds\n")
    print("\n".join(summary_table(trials)))

    obeying = [t for t in trials if t.model != "echo"]
    print("\nattack success by payload (either goal; echo excluded)")
    print("\n".join(payload_table(obeying)))

    if args.cmd:
        return
    print("\ndetector check, config=none: does the canary design score quoting as obedience?")
    print("canary   model    content-ASR")
    for split in (False, True):
        for name, m in models:
            if name not in ("naive", "echo"):
                continue
            ts = run_grid([(name, m)], configs=["none"], seeds=args.seeds, split=split)
            ts = [t for t in ts if t.goal == "content"]
            print(f"{'split' if split else 'literal':<9}{name:<9}{rate(ts, 'content'):>11.0%}")


if __name__ == "__main__":
    main()
