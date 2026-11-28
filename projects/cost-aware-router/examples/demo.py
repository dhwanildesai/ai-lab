"""Fit routers on one eval log, score them on another. `--records f.jsonl` uses your own log."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # run without installing

from cost_router.experiment import run, sweep, table
from cost_router.records import load_jsonl, simulate, split

DRIFT = {"classify": 0.3, "summarize": 0.3}  # easy categories get harder after the router is fit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, help="JSONL eval log (see README for the schema)")
    parser.add_argument("--n", type=int, default=2000, help="simulated tasks per split")
    parser.add_argument("--max-drop", type=float, default=0.01, help="allowed accuracy drop")
    args = parser.parse_args()
    if args.n < 1 or not 0 <= args.max_drop < 1:
        parser.error("--n must be >= 1 and 0 <= --max-drop < 1")

    if args.records:
        train, test = split(load_jsonl(args.records))
        print(f"{args.records.name}: {len(train)} train / {len(test)} test records\n")
        print(table(run(train, test, args.max_drop)))
        return

    train = simulate(args.n, seed=1)
    same = simulate(args.n, seed=2)
    drifted = simulate(args.n, seed=2, drift=DRIFT)
    drop = f"max drop {args.max_drop * 100:g} pt"
    print(f"SIMULATED models. Fit on {len(train)} tasks (seed 1), {drop}, large = 15x small cost\n")
    print(f"== held-out, same distribution, {len(same)} tasks (seed 2)")
    print(table(run(train, same, args.max_drop)) + "\n")
    print("== accuracy budget sweep; drift = classify and summarize +0.3 difficulty at test time")
    print(sweep(train, [("same", same), ("drift", drifted)], [0.005, 0.01, 0.02, 0.05, 0.10]))


if __name__ == "__main__":
    main()
