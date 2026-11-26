import importlib.util
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
spec = importlib.util.spec_from_file_location("ledger_claude", EXAMPLES / "claude.py")
claude = importlib.util.module_from_spec(spec)
spec.loader.exec_module(claude)


def test_concurrent_identical_prompts_make_one_call(monkeypatch, tmp_path):
    calls = []
    gate = threading.Event()

    def fake_run(*args, **kwargs):
        calls.append(1)
        gate.wait(0.2)
        return type("Done", (), {"stdout": f'{{"result": "reply {len(calls)}"}}'})()

    monkeypatch.setattr(claude, "CACHE", tmp_path / "cache.json")
    monkeypatch.setattr(claude, "_cache", {})
    monkeypatch.setattr(claude.subprocess, "run", fake_run)
    with ThreadPoolExecutor(4) as pool:
        replies = set(pool.map(lambda _: claude.ask("m", "s", "p"), range(4)))
    assert len(calls) == 1 and replies == {"reply 1"}
