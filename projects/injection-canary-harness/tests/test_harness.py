from __future__ import annotations

import random
import sys

import pytest
from canary_harness.agent import run_episode
from canary_harness.canaries import PAYLOADS, detect, make_canary, render
from canary_harness.experiment import rate, run_grid
from canary_harness.models import SIMULATED, CommandModel
from canary_harness.scenarios import SCENARIOS

NAIVE, CUE, MARKER, ECHO = SIMULATED
SC = SCENARIOS[0]


def episode(model, config, payload="classic", goal="content", split=True, seed=0):
    rng = random.Random(seed)
    canary = make_canary(rng)
    t = run_episode(model, SC, config, render(payload, goal, canary, split), rng)
    return t, detect(t, canary)


def test_split_injection_never_contains_the_joined_token():
    canary = make_canary(random.Random(1))
    for payload in PAYLOADS:
        for goal in ("action", "content"):
            assert canary.token not in render(payload, goal, canary, split=True)
            assert canary.token in render(payload, goal, canary, split=False)


def test_clean_runs_never_trigger_the_detector():
    for model in SIMULATED:
        for sc in SCENARIOS:
            rng = random.Random(sc.name)
            t = run_episode(model, sc, "none", None, rng)
            assert not detect(t, make_canary(rng)).obeyed
            assert sc.expected in t.answer


def test_literal_canary_scores_quoting_as_obedience_split_does_not():
    _, literal = episode(ECHO, "none", split=False)
    _, split = episode(ECHO, "none", split=True)
    assert literal.content and not split.content


def test_naive_obeys_both_goals_undefended():
    assert episode(NAIVE, "none", goal="action")[1].action
    assert episode(NAIVE, "none", goal="content")[1].content


def test_plan_then_execute_blocks_actions_but_not_content():
    t, v = episode(NAIVE, "plan_then_execute", goal="action")
    assert not v.action and v.attempted
    assert [c["tool"] for c in t.calls] == [SC.tool]  # only the planned call ran
    assert episode(NAIVE, "plan_then_execute", goal="content")[1].content


def test_nonce_markers_defeat_delimiter_escape_static_markers_do_not():
    assert episode(MARKER, "spotlight_static", "delimiter_escape")[1].content
    assert not episode(MARKER, "spotlight_nonce", "delimiter_escape")[1].content
    assert not episode(MARKER, "spotlight_static", "classic")[1].content


def test_cue_filter_only_stops_phrasings_it_knows():
    assert not episode(CUE, "none", "classic")[1].content
    assert episode(CUE, "none", "polite")[1].content
    assert episode(CUE, "none", "hidden")[1].content


def test_sanitizer_drops_benign_imperative_and_loses_utility():
    doc = next(s for s in SCENARIOS if s.name == "upgrade_doc")
    t = run_episode(NAIVE, doc, "sanitize", None, random.Random(0))
    assert doc.expected not in t.answer
    assert doc.expected in run_episode(NAIVE, doc, "none", None, random.Random(0)).answer


def test_harness_refuses_unoffered_tools_in_act_phase():
    class Rogue:
        def __call__(self, req):
            if not any(m["role"] == "tool" for m in req["messages"]):
                return {"tool": "delete_repo", "args": {}}
            return {"answer": "done"}

    t = run_episode(Rogue(), SC, "none", None, random.Random(0))
    assert t.calls == [] and t.blocked == [{"tool": "delete_repo", "args": {}}]


def test_grid_is_deterministic_and_sized():
    models = [(m.name, m) for m in (NAIVE, ECHO)]
    a = run_grid(models, configs=["none", "spotlight_nonce"], seeds=2)
    b = run_grid(models, configs=["none", "spotlight_nonce"], seeds=2)
    assert a == b
    assert len(a) == 2 * 2 * len(SCENARIOS) * (1 + 2 * len(PAYLOADS)) * 2
    assert rate([t for t in a if t.model == "echo"], "content") == 0


def test_command_model_round_trip():
    script = (
        "import json,sys; r=json.load(sys.stdin); "
        "print(json.dumps({'answer': r['phase']+':'+str(len(r['tools']))}))"
    )
    model = CommandModel(f'"{sys.executable}" -c "{script}"')
    t = run_episode(model, SC, "none", None, random.Random(0))
    assert t.answer == "act:4"


def test_command_model_rejects_non_object():
    model = CommandModel(f'"{sys.executable}" -c "print(1)"')
    with pytest.raises(TypeError):
        model({"phase": "act"})
