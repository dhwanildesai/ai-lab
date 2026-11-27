"""Real-model benchmark: compact a long session three times, then ask what survived.

python examples/bench.py --seeds 0 1            # development seeds
python examples/bench.py --seeds 100-109        # held-out report
python examples/bench.py --seeds 100-109 --offline   # replay committed replies, free
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), str(HERE.parent / "src")]

from claude import ask
from context_ledger import Ledger, mask_observations, render, tokens, truncate
from sessions import build

ANSWERER = "claude-haiku-5-5"
SUMMARIZER = "claude-sonnet-5-5"  # deliberately stronger than the answerer: a strong baseline
BUDGET = 1500
RECALL_TOKENS = 200

FREEFORM = (
    "You compact the history of a coding session so another agent can continue the work. "
    "Write a summary of at most {words} words. Reply with the summary only."
)
STRUCTURED = (
    "You maintain a running summary of a coding session so another agent can continue the work. "
    "Merge the new events into the existing summary. Use these sections: Goal; User constraints "
    "(quote the user exactly); Current values (latest only, with exact names); Errors (exact codes "
    "and paths); Decisions and findings; Next steps. Never drop a constraint, identifier, number, "
    "path or error code unless a newer value replaces it. At most {words} words. Reply with the "
    "summary only."
)
ANSWER = (
    "You are a coding agent resuming work. Answer each question using ONLY the context. "
    "Reply with one JSON object mapping question id to the bare value only, with no explanation. "
    'Use "unknown" if the context does not contain the answer.'
)
ANSWER_RECALL = ANSWER + (
    ' Instead of "unknown" you may answer "RECALL: <search keywords>" once per question to search '
    "the full earlier history."
)
METHODS = ["full", "truncate", "mask", "summary", "structured", "structured+recall",
           "ledger", "ledger+recall", "hybrid+recall"]  # fmt: skip


def summarize(segments, system: str, budget: int, offline: bool) -> str:
    words = budget * 2 // 3
    summary = ""
    for segment in segments:  # each round sees only the last summary plus what is new
        history = "\n".join(render(e) for e in segment)
        prompt = f"EXISTING SUMMARY:\n{summary or '(none)'}\n\nNEW EVENTS:\n{history}"
        summary = ask(SUMMARIZER, system.format(words=words), prompt, offline)[: budget * 4]
    return summary


def parse(reply: str) -> dict:
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    try:
        return {k: str(v) for k, v in json.loads(match.group(0)).items()} if match else {}
    except ValueError:
        return {}


def grade(probe, answer: str) -> str:
    plain = re.sub(r"(?<=\d)\s*ms\b", "", answer.lower())  # "37ms" and "37" are the same answer

    def has(value):
        return re.search(rf"(?<![\w]){re.escape(value.lower())}(?![\w])", plain)

    right = has(probe.answer.rstrip("/"))
    old = has(probe.stale) if probe.stale else None
    # Mentioning the outdated value after the current one is fine; leading with it is not.
    if right and (old is None or right.start() < old.start()):
        return "correct"
    low = answer.strip().lower()
    return "abstain" if not low or low.startswith(("unknown", "recall")) else "wrong"


def run_one(seed: int, method: str, budget: int, rounds: int, offline: bool) -> dict:
    segments, probes = build(seed, rounds)
    events = [e for s in segments for e in s]
    book = Ledger()
    book.extend(events)
    base = method.split("+")[0]
    if base == "full":
        context = "\n".join(render(e) for e in events)
    elif base == "truncate":
        context = truncate(events, budget)
    elif base == "mask":
        context = mask_observations(events, budget)
    elif base == "ledger":
        context = book.compact(budget)
    elif base == "hybrid":  # half the budget to a model summary, half to the ledger
        notes = summarize(segments, STRUCTURED, budget // 2, offline)
        context = f"{book.compact(budget // 2)}\n\n## Running summary\n{notes}"
    else:
        system = FREEFORM if base == "summary" else STRUCTURED
        context = summarize(segments, system, budget, offline)

    recall = method.endswith("+recall")
    questions = "\n".join(f"{p.id}: {p.question}" for p in probes)
    prompt = f"CONTEXT:\n{context}\n\nQUESTIONS:\n{questions}"
    answers = parse(ask(ANSWERER, ANSWER_RECALL if recall else ANSWER, prompt, offline))
    recalls = 0
    if recall:
        asked = [p for p in probes if answers.get(p.id, "").upper().startswith("RECALL")]
        recalls = len(asked)
        if asked:
            found = "\n\n".join(
                f"For {p.id} (search: {answers[p.id][7:].strip()}):\n"
                + book.recall(answers[p.id][7:], RECALL_TOKENS)
                for p in asked
            )
            again = "\n".join(f"{p.id}: {p.question}" for p in asked)
            second = f"CONTEXT:\n{context}\n\nSEARCH RESULTS:\n{found}\n\nQUESTIONS:\n{again}"
            answers.update(parse(ask(ANSWERER, ANSWER, second, offline)))
    return {
        "seed": seed,
        "method": method,
        "tokens": tokens(context),
        "recalls": recalls,
        "compaction_calls": rounds if base in ("summary", "structured", "hybrid") else 0,
        "grades": {p.id: grade(p, answers.get(p.id, "")) for p in probes},
        "categories": {p.id: p.category for p in probes},
        "answers": answers,
    }


def interval(values, rounds: int = 4000):
    rng = random.Random(0)
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(rounds))
    return means[int(rounds * 0.025)], means[int(rounds * 0.975)]


def report(rows, budget: int, rounds: int) -> str:
    seeds = sorted({r["seed"] for r in rows})
    by = {(r["method"], r["seed"]): r for r in rows}
    score = {
        m: [sum(g == "correct" for g in by[m, s]["grades"].values()) / len(by[m, s]["grades"]) for s in seeds]
        for m in METHODS
    }  # fmt: skip
    cats = list(dict.fromkeys(rows[0]["categories"].values()))
    out = [
        (
            f"{len(seeds)} sessions, {len(rows[0]['grades'])} probes each, budget {budget} est. "
            f"tokens, {rounds} compaction rounds. answerer={ANSWERER} summarizer={SUMMARIZER}"
        ),
        "",
        f"{'method':<19}{'correct':>8}  {'95% CI':<13}{'wrong':>6}{'tokens':>8}{'recalls':>8}{'summ.calls':>11}  "
        + "".join(f"{c[:13]:>15}" for c in cats),
    ]
    for m in METHODS:
        mine = [by[m, s] for s in seeds]
        grades = [(r["categories"][q], g) for r in mine for q, g in r["grades"].items()]
        low, high = interval(score[m])
        per = "".join(
            f"{sum(g == 'correct' for c2, g in grades if c2 == c) / sum(c2 == c for c2, _ in grades):>15.0%}"
            for c in cats
        )
        out.append(
            f"{m:<19}{sum(score[m]) / len(seeds):>8.1%}  [{low:.0%}, {high:.0%}]".ljust(42)
            + f"{sum(g == 'wrong' for _, g in grades) / len(grades):>6.1%}"
            f"{sum(r['tokens'] for r in mine) / len(mine):>8.0f}"
            f"{sum(r['recalls'] for r in mine) / len(mine):>8.1f}"
            f"{sum(r['compaction_calls'] for r in mine) / len(mine):>11.0f}  {per}"
        )
    out += ["", "paired difference in correct, ledger+recall minus other (95% CI over sessions):"]
    for m in METHODS:
        if m == "ledger+recall":
            continue
        diff = [a - b for a, b in zip(score["ledger+recall"], score[m])]
        low, high = interval(diff)
        out.append(
            f"  vs {m:<18}{sum(diff) / len(diff) * 100:>+6.1f} points  [{low * 100:+.1f}, {high * 100:+.1f}]"
        )
    return "\n".join(out)  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", nargs="+", default=["100-109"])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--budget", type=int, default=BUDGET)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    seeds = []
    for item in args.seeds:
        low, _, high = item.partition("-")
        seeds += range(int(low), int(high or low) + 1)
    jobs = [(s, m, args.budget, args.rounds) for s in seeds for m in METHODS]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(lambda j: run_one(*j, args.offline), jobs))
    text = report(rows, args.budget, args.rounds)
    tag = f"{seeds[0]}-{seeds[-1]}-b{args.budget}-r{args.rounds}"
    (HERE / "live").mkdir(exist_ok=True)
    (HERE / "live" / f"results-{tag}.txt").write_text(text + "\n")
    (HERE / "live" / f"rows-{tag}.json").write_text(json.dumps(rows, indent=1))
    print(text)


if __name__ == "__main__":
    main()
