"""Offline checks on the committed real-model (Claude) answers. No network, no CLI needed."""

import importlib.util
from pathlib import Path

from tool_fuzzer import TASKS, TOOLS

EX = Path(__file__).resolve().parents[1] / "examples"
spec = importlib.util.spec_from_file_location("claude_selector", EX / "claude_selector.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


def test_every_cached_reply_is_a_valid_tool_name():
    cache = cs.load_cache()
    assert len(cache) == 768
    assert set(cache.values()) <= {t.name for t in TOOLS}


def test_baseline_prompts_are_all_cached_and_correct():
    cache = cs.load_cache()
    hits = 0
    for task in TASKS:
        payload = {"query": task.query, "tools": [t._asdict() for t in TOOLS]}
        assert cs.key(payload) in cache
        hits += cache[cs.key(payload)] == task.expected
    assert hits == len(TASKS)  # the 100.0% baseline reported in the README
