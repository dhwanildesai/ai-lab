"""Run the full experiment against real Claude, in parallel, through the `--cmd` adapter.

python examples/live_run.py --count            # how many unique model calls are needed
python examples/live_run.py --seeds 3          # fill the cache, then print the tables
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import claude_selector as cs
from tool_fuzzer import TASKS, TOOLS, CommandSelector, accuracy, measure


class Collect:
    """Records every prompt the experiment would send; answers nothing."""

    def __init__(self) -> None:
        self.payloads: dict[str, dict] = {}

    def select(self, query, tools):
        p = {"query": query, "tools": [t._asdict() for t in tools]}
        self.payloads[cs.key(p)] = p


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--count", action="store_true")
    args = ap.parse_args()

    collector = Collect()
    accuracy(collector, TOOLS, TASKS)
    measure(collector, TOOLS, TASKS, args.seeds)
    cache = cs.load_cache()
    todo = {k: p for k, p in collector.payloads.items() if k not in cache}
    print(
        f"model={cs.MODEL} unique prompts={len(collector.payloads)} cached={len(cache)} todo={len(todo)}"
    )
    if args.count:
        return

    def work(item):
        k, p = item
        for attempt in range(3):
            try:
                return k, cs.ask(p)
            except Exception as exc:  # noqa: BLE001 - infrastructure fault: retry, never record as an answer
                last = exc
        raise RuntimeError(f"giving up on {k}: {last}")

    with ThreadPoolExecutor(args.workers) as pool:
        for n, (k, reply) in enumerate(pool.map(work, todo.items()), 1):
            cache[k] = reply
            if n % 25 == 0:
                cs.save_cache(cache)
                print(f"  {n}/{len(todo)} done", flush=True)
    cs.save_cache(cache)

    names = {t.name for t in TOOLS}
    invalid = sum(1 for r in cache.values() if r not in names)
    print(f"model replies that were not a valid tool name: {invalid}/{len(cache)}")
    selector = CommandSelector([sys.executable, str(HERE / "claude_selector.py")])
    print(f"\n== {cs.MODEL} (REAL): baseline accuracy {accuracy(selector, TOOLS, TASKS):.1%}")
    print("all tools mutated    acc   delta  95% CI (points)  p_holm  flips")
    for e in measure(selector, TOOLS, TASKS, args.seeds):
        ci = f"[{e.low * 100:+.1f}, {e.high * 100:+.1f}]"
        print(f"  {e.mutation:<15}{e.accuracy:>7.1%}{e.delta * 100:>+8.1f}  "
              f"{ci:<15}{e.p_holm:>8.3f}{e.flips:>7.1%}")  # fmt: skip


if __name__ == "__main__":
    main()
