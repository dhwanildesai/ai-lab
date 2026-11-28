from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from cost_router.experiment import paired_delta_ci, run, score, sweep, table
from cost_router.policies import Cascade, CategoryGate, Fixed, Oracle, Outcome
from cost_router.records import Record, dump_jsonl, load_jsonl, simulate, split

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo.py"


def rec(cat="a", small=True, large=True, agree=True, i=0, cost=1.0):
    return Record(f"{cat}{i}", cat, small, large, agree, cost, cost * 15)


def accuracy(policy, records):
    return sum(policy.route(r).correct for r in records) / len(records)


def test_simulate_is_deterministic_and_drift_hurts_small_model():
    assert simulate(300, seed=4) == simulate(300, seed=4)
    assert simulate(300, seed=4) != simulate(300, seed=5)
    base = simulate(3000, seed=4)
    harder = simulate(3000, seed=4, drift={c: 0.3 for c in ("extract", "classify")})
    assert accuracy(Fixed("small"), harder) < accuracy(Fixed("small"), base)


def test_split_is_stable_disjoint_and_complete():
    records = simulate(500, seed=1)
    train, test = split(records)
    assert split(records) == (train, test)
    assert {r.task_id for r in train}.isdisjoint(r.task_id for r in test)
    assert len(train) + len(test) == 500
    assert 150 < len(test) < 350


def test_jsonl_round_trip_and_bad_rows(tmp_path):
    records = simulate(20, seed=3)
    path = tmp_path / "log.jsonl"
    dump_jsonl(records, path)
    assert load_jsonl(path) == records
    path.write_text('{"task_id": "x", "category": "a"}\n')
    with pytest.raises(ValueError, match="log.jsonl:1"):
        load_jsonl(path)


def test_fixed_rejects_unknown_tier():
    with pytest.raises(ValueError):
        Fixed("medium")


def test_cascade_cost_accounting():
    assert Cascade().route(rec(small=False, agree=True)) == Outcome(False, 2.0)
    assert Cascade().route(rec(small=False, agree=False)) == Outcome(True, 17.0, escalated=True)


def test_oracle_is_an_upper_bound_on_accuracy_and_never_costs_more_than_large():
    records = simulate(1000, seed=2)
    oracle = [Oracle().route(r) for r in records]
    either = sum(r.small_correct or r.large_correct for r in records) / len(records)
    assert sum(o.correct for o in oracle) / len(records) == either
    for r, o in zip(records, oracle):
        assert o.cost <= r.large_cost
    for policy in (Fixed("small"), Fixed("large"), Cascade()):
        assert accuracy(policy, records) <= either


@pytest.mark.parametrize("max_drop", [0.0, 0.01, 0.03, 0.1])
@pytest.mark.parametrize("cheap", [Fixed("small"), Cascade()])
def test_fitted_gate_meets_its_budget_on_train(max_drop, cheap):
    train = simulate(1500, seed=7)
    gate = CategoryGate.fit(train, cheap, Fixed("large"), max_drop, "g")
    assert accuracy(gate, train) >= accuracy(Fixed("large"), train) - max_drop - 1e-12


def test_gate_takes_free_savings_and_refuses_costly_ones():
    free = [rec("easy", i=i) for i in range(10)]  # small always as good as large
    costly = [rec("hard", small=False, i=i) for i in range(10)]
    gate = CategoryGate.fit(free + costly, Fixed("small"), Fixed("large"), 0.0, "g")
    assert gate.allowed == frozenset({"easy"})
    assert gate.route(costly[0]) == Outcome(True, 15.0)


def test_paired_ci():
    same = [Outcome(i % 2 == 0, 1.0) for i in range(50)]
    assert paired_delta_ci(same, same) == (0.0, 0.0)
    worse = [Outcome(False, 1.0) if i < 10 else o for i, o in enumerate(same)]
    lo, hi = paired_delta_ci(worse, same)
    assert lo < -5 / 50 < hi < 0


def test_run_scores_every_policy_and_tables_render():
    train, test = simulate(400, seed=1), simulate(400, seed=2)
    scores = run(train, test, 0.02)
    names = [s.name for s in scores]
    assert names == [
        "always_small",
        "always_large",
        "cascade",
        "category",
        "category+cascade",
        "oracle",
    ]
    large = scores[1]
    assert large.delta_ci == (0.0, 0.0)
    assert score(Fixed("large"), test, Fixed("large")) == large
    assert "cheap on:" in table(scores)
    assert sweep(train, [("same", test)], [0.01]).count("\n") == 2
    with pytest.raises(ValueError):
        run([], test, 0.01)
    with pytest.raises(ValueError):
        run(train, [], 0.01)


def test_demo_runs_on_a_recorded_log(tmp_path):
    path = tmp_path / "evals.jsonl"
    dump_jsonl(simulate(200, seed=9), path)
    out = subprocess.run(
        [sys.executable, str(DEMO), "--records", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "evals.jsonl:" in out and "category+cascade" in out
