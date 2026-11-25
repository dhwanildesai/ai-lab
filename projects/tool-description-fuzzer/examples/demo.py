"""Print both result tables. `--cmd "..."` measures an external (e.g. live) selector instead."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # run without installing

from tool_fuzzer import (
    MUTATIONS,
    TASKS,
    TOOLS,
    BM25Selector,
    CommandSelector,
    LeadBiasedSelector,
    accuracy,
    hijack,
    measure,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--cmd", help="command: JSON on stdin, tool name on stdout")
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be at least 1")

    if args.cmd:
        selectors = {"external": CommandSelector(shlex.split(args.cmd))}
    else:
        selectors = {
            "bm25 (simulated)": BM25Selector(),
            "lead-biased (simulated)": LeadBiasedSelector(),
        }
    print(f"{len(TOOLS)} tools, {len(TASKS)} tasks, {args.seeds} seeds per mutation")
    for label, selector in selectors.items():
        print(f"\n== {label}: baseline accuracy {accuracy(selector, TOOLS, TASKS):.1%}")
        print("all tools mutated    acc   delta  95% CI (points)  p_holm  flips")
        for e in measure(selector, TOOLS, TASKS, args.seeds):
            ci = f"[{e.low * 100:+.1f}, {e.high * 100:+.1f}]"
            print(
                f"  {e.mutation:<15}{e.accuracy:>7.1%}{e.delta * 100:>+8.1f}  "
                f"{ci:<15}{e.p_holm:>8.3f}{e.flips:>7.1%}"
            )
        if args.cmd:
            continue  # one-at-a-time needs tools x seeds x tasks calls: too many for a live model
        print("one tool mutated   own recall       stolen from others")
        for name in MUTATIONS:
            h = hijack(selector, TOOLS, TASKS, name, args.seeds)
            print(f"  {name:<15}{h.own_before:>7.1%} -> {h.own_after:<7.1%}{h.stolen:>10.1%}")


if __name__ == "__main__":
    main()
