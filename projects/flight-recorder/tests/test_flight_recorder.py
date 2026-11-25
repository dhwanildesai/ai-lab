import random

import pytest
from flight_recorder import DivergenceError, Recorder, Replayer, Trace, diff_traces


def agent(llm, tool, goal):
    ctx = goal
    for _ in range(6):
        step = llm(ctx)
        if step == "DONE":
            return ctx
        ctx += "|" + str(tool(step))
    return ctx


def make_llm(seed):
    rng = random.Random(seed)
    return lambda ctx: "DONE" if rng.random() < 0.3 else f"q{rng.randint(0, 9)}"


def test_replay_reproduces_100_percent_of_random_runs():
    for seed in range(200):
        rec = Recorder()
        out = agent(rec.llm(make_llm(seed)), rec.tool("t", lambda q: q.upper()), "go")
        rp = Replayer(rec.trace)
        assert agent(rp.llm(), rp.tool("t"), "go") == out
        assert rp.finished()


def test_jsonl_roundtrip(tmp_path):
    rec = Recorder()
    agent(rec.llm(make_llm(1)), rec.tool("t", str), "go")
    rec.trace.save(tmp_path / "t.jsonl")
    assert diff_traces(rec.trace, Trace.load(tmp_path / "t.jsonl")) is None


def test_changed_input_is_a_divergence():
    rec = Recorder()
    agent(rec.llm(make_llm(2)), rec.tool("t", str), "go")
    rp = Replayer(rec.trace)
    with pytest.raises(DivergenceError):
        agent(rp.llm(), rp.tool("t"), "different goal")


def test_wrong_tool_is_a_divergence():
    rec = Recorder()
    rec.tool("a", str)(1)
    with pytest.raises(DivergenceError):
        Replayer(rec.trace).tool("b")(1)


def test_extra_call_and_missing_call_detected():
    rec = Recorder()
    rec.tool("a", str)(1)
    rp = Replayer(rec.trace)
    rp.tool("a")(1)
    with pytest.raises(DivergenceError):
        rp.tool("a")(1)
    assert not Replayer(rec.trace).finished()


def test_errors_are_recorded_and_replayed():
    def boom(_):
        raise ValueError("bad")

    rec = Recorder()
    with pytest.raises(ValueError):
        rec.tool("t", boom)(1)
    assert rec.trace.events[0].error == "ValueError: bad"
    with pytest.raises(RuntimeError, match="ValueError: bad"):
        Replayer(rec.trace).tool("t")(1)


def test_diff_finds_first_divergence():
    a, b = Recorder(), Recorder()
    a.tool("t", str)(1)
    b.tool("t", str)(2)
    d = diff_traces(a.trace, b.trace)
    assert d and d.index == 0 and "input" in d.reason
