"""Replays the committed trace of a real Claude run. No network, no API key, no CLI."""

import importlib.util
from pathlib import Path

import pytest
from flight_recorder import DivergenceError, Replayer, Trace

EXAMPLES = Path(__file__).parent.parent / "examples"
spec = importlib.util.spec_from_file_location("real_agent", EXAMPLES / "real_agent.py")
real_agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real_agent)

TOOLS = ("list_repos", "get_repo_stats", "calculate")


def _replay(trace, system=real_agent.SYSTEM):
    rp = Replayer(trace)
    tools = {n: rp.tool(n) for n in TOOLS}
    answer = real_agent.run_agent(rp.llm(real_agent.MODEL), tools, real_agent.QUESTION, system)
    return answer, rp


def test_real_claude_run_replays_identically():
    trace = Trace.load(real_agent.TRACE)
    answer, rp = _replay(trace)
    assert rp.finished()
    assert "gamma-evals" in answer and "205" in answer
    assert answer == trace.events[-1].output["content"][0]["text"]


def test_prompt_change_is_caught_against_real_trace():
    with pytest.raises(DivergenceError, match="event 0"):
        _replay(Trace.load(real_agent.TRACE), system=real_agent.SYSTEM + " Be verbose.")
