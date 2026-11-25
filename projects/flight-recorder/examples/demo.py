"""Record a toy agent, then replay it offline and show a regression being caught."""

import random

from flight_recorder import DivergenceError, Recorder, Replayer


def run_agent(llm, search, goal: str) -> str:
    """Toy loop: LLM asks for a search until it says DONE."""
    ctx = goal
    for _ in range(5):
        step = llm(ctx)
        if step.startswith("DONE"):
            return step
        ctx += " | " + search(step)
    return "gave up"


def flaky_llm(ctx: str) -> str:  # nondeterministic on purpose
    return random.choice(["q:alpha", "q:beta"]) if ctx.count("|") < 2 else "DONE ok"


def search(q: str) -> str:
    return f"result({q})"


rec = Recorder()
out = run_agent(rec.llm(flaky_llm), rec.tool("search", search), "find stuff")
rec.trace.save("run.jsonl")
print("recorded:", out, f"({len(rec.trace.events)} events)")

rp = Replayer(rec.trace)
assert run_agent(rp.llm(), rp.tool("search"), "find stuff") == out and rp.finished()
print("replay: identical, offline, deterministic")

try:  # a code change makes the agent send a different goal
    rp2 = Replayer(rec.trace)
    run_agent(rp2.llm(), rp2.tool("search"), "find OTHER stuff")
except DivergenceError as e:
    print("regression caught:", e)
