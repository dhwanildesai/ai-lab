"""The published tables must replay from the committed model replies. No network, no CLI."""

import importlib.util
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
spec = importlib.util.spec_from_file_location("ledger_bench", EXAMPLES / "bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


@pytest.mark.parametrize(("budget", "rounds"), [(1500, 3), (700, 6)])
def test_held_out_table_replays_offline(budget, rounds):
    rows = [
        bench.run_one(seed, method, budget, rounds, offline=True)
        for seed in range(100, 108)
        for method in bench.METHODS
    ]
    saved = (EXAMPLES / "live" / f"results-100-107-b{budget}-r{rounds}.txt").read_text()
    assert bench.report(rows, budget, rounds) + "\n" == saved
