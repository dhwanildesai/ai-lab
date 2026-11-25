import random
import subprocess
import sys

import pytest
from tool_fuzzer import (
    MUTATIONS,
    TASKS,
    TOOLS,
    BM25Selector,
    CommandSelector,
    LeadBiasedSelector,
    Task,
    Tool,
    accuracy,
    hijack,
    measure,
    mutate,
)
from tool_fuzzer.experiment import bootstrap_ci, holm, sign_flip_p
from tool_fuzzer.mutations import BOILERPLATE, sentences

SELECTORS = [BM25Selector(), LeadBiasedSelector()]


def by_name(effects):
    return {e.mutation: e for e in effects}


def test_fixture_is_balanced():
    names = [t.name for t in TOOLS]
    assert len(set(names)) == len(names) == 12
    assert len({t.query for t in TASKS}) == len(TASKS) == 48
    assert all(sum(t.expected == n for t in TASKS) == 4 for n in names)
    assert all(len(sentences(t.description)) == 3 for t in TOOLS)


@pytest.mark.parametrize("name", list(MUTATIONS))
def test_mutations_are_reproducible_and_keep_names(name):
    out = mutate(TOOLS, name, 7)
    assert out == mutate(TOOLS, name, 7)
    assert [t.name for t in out] == [t.name for t in TOOLS]
    assert all(t.description for t in out)
    if name != "identity":
        assert out != TOOLS


def test_seed_changes_random_mutations():
    assert mutate(TOOLS, "synonyms", 1) != mutate(TOOLS, "synonyms", 2)


def test_only_mutates_one_tool():
    out = mutate(TOOLS, "boilerplate", 0, only="run_sql")
    assert [a.name for a, b in zip(TOOLS, out) if a != b] == ["run_sql"]
    with pytest.raises(ValueError):
        mutate(TOOLS, "boilerplate", 0, only="nope")


def test_individual_mutations_do_what_they_say():
    original = TOOLS[0].description
    got = {n: mutate(TOOLS, n, 3)[0].description for n in MUTATIONS}
    assert got["first_sentence"] == "Find files by name or path pattern."
    assert "Do not" not in got["drop_negative"] and "Use to" in got["drop_negative"]
    assert got["boilerplate"] == BOILERPLATE + " " + original
    assert sorted(sentences(got["reorder"])) == sorted(sentences(original))
    assert got["stuffing"].startswith(original + " Also handles: ")
    assert sorted(got["typos"]) == sorted(original)


@pytest.mark.parametrize("selector", SELECTORS)
def test_selector_ignores_registry_order(selector):
    expected = [selector.select(t.query, TOOLS) for t in TASKS]
    for seed in range(5):
        shuffled = list(TOOLS)
        random.Random(seed).shuffle(shuffled)
        assert [selector.select(t.query, shuffled) for t in TASKS] == expected


@pytest.mark.parametrize("selector", SELECTORS)
def test_selector_abstains_without_overlap(selector):
    assert selector.select("zzz qqq", TOOLS) is None
    assert selector.select("anything", []) is None


@pytest.mark.parametrize("selector", SELECTORS)
def test_aa_control_is_exactly_zero(selector):
    e = by_name(measure(selector, TOOLS, TASKS, seeds=2))["identity"]
    assert (e.delta, e.low, e.high, e.flips, e.p_holm) == (0, 0, 0, 0, 1)
    h = hijack(selector, TOOLS, TASKS, "identity", seeds=1)
    assert h.own_before == h.own_after and h.stolen == 0


def test_reorder_separates_order_blind_from_order_sensitive():
    assert by_name(measure(BM25Selector(), TOOLS, TASKS, seeds=3))["reorder"].flips == 0
    assert by_name(measure(LeadBiasedSelector(), TOOLS, TASKS, seeds=3))["reorder"].flips > 0


class Oracle:
    """Right for every task unless the expected tool's description is boilerplated."""

    def select(self, query, tools):
        expected = {t.query: t.expected for t in TASKS}[query]
        tool = next(t for t in tools if t.name == expected)
        return None if tool.description.startswith(BOILERPLATE) else expected


def test_known_effect_is_recovered_exactly():
    effects = by_name(measure(Oracle(), TOOLS, TASKS, seeds=2))
    assert effects["boilerplate"].delta == -1 and effects["boilerplate"].flips == 1
    assert effects["boilerplate"].p_holm < 0.01
    assert all(e.delta == 0 for n, e in effects.items() if n != "boilerplate")


def test_hijack_counts_stolen_tasks():
    class Greedy:
        def select(self, query, tools):
            for t in tools:
                if "Also handles" in t.description:
                    return t.name
            return query

    tools = [Tool("a", "Alpha things."), Tool("b", "Bravo stuff.")]
    tasks = [Task("a", "a"), Task("b", "b")]
    h = hijack(Greedy(), tools, tasks, "stuffing", seeds=2)
    assert (h.own_before, h.own_after, h.stolen) == (1, 1, 1)


def test_statistics():
    adjusted = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})
    assert sign_flip_p([0.0] * 10) == 1
    assert sign_flip_p([1.0] * 12) < 0.01
    assert sign_flip_p([1.0, -1.0] * 6) == 1
    low, high = bootstrap_ci([0.0, 1.0] * 20)
    assert 0.3 < low < 0.5 < high < 0.7


def test_command_selector_round_trip_and_failure():
    script = "import json,sys; d=json.load(sys.stdin); print(d['tools'][1]['name'])"
    assert CommandSelector([sys.executable, "-c", script]).select("q", TOOLS) == "grep_text"
    assert CommandSelector([sys.executable, "-c", "pass"]).select("q", TOOLS) is None
    with pytest.raises(subprocess.CalledProcessError):
        CommandSelector([sys.executable, "-c", "raise SystemExit(3)"]).select("q", TOOLS)


def test_accuracy_counts_abstention_as_wrong():
    tasks = [Task("zzz", "run_sql"), Task("aggregate rows", "run_sql")]
    assert accuracy(BM25Selector(), TOOLS, tasks) == 0.5
