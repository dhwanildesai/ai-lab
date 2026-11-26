import importlib.util
import io
import json
from pathlib import Path

from context_ledger import Event, Ledger, mask_observations, tokens, truncate

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "after_compact.py"
spec = importlib.util.spec_from_file_location("after_compact", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

RULE = "Please never run migrations against the production database."


def session(noise=40):
    events = [Event(1, "user", RULE), Event(2, "user", "Set api.timeout_s=30 for now.")]
    for i in range(noise):
        events.append(Event(len(events) + 1, "tool", "log line\n" * 60, f"pytest run {i}"))
    events.append(Event(len(events) + 1, "assistant", "I chose Redis because ops runs it."))
    events.append(Event(len(events) + 1, "user", "Change it: api.timeout_s=45."))
    return events


def ledger(events):
    out = Ledger()
    out.extend(events)
    return out


def test_budget_is_respected_at_every_size():
    book = ledger(session())
    for budget in (150, 400, 1000, 4000):
        assert tokens(book.compact(budget)) <= budget


def test_user_constraint_survives_verbatim_where_truncation_loses_it():
    events = session()
    assert RULE in ledger(events).compact(800)
    assert RULE not in truncate(events, 800)


def test_newer_value_supersedes_and_says_what_it_replaced():
    assert "api.timeout_s = 45 (#44; was 30)" in ledger(session()).compact(1200)


def test_repeated_compaction_does_not_compound_loss():
    events = session()
    once = ledger(events)
    stepwise = Ledger()
    for start in range(0, len(events), 7):
        stepwise.extend(events[start : start + 7])
        stepwise.compact(500)
    assert stepwise.compact(800) == once.compact(800)


def test_omissions_are_declared():
    assert "older omitted: use recall" in ledger(session()).compact(500)


def test_recall_restores_a_buried_tool_fact():
    events = session()
    events.insert(5, Event(99, "tool", "ok\npool saturates at 12 connections\nok", "load test"))
    assert "12 connections" in ledger(events).recall("pool saturates connections")
    assert ledger(events).recall("zzzz qqqq") == "no match"


def test_masking_keeps_only_recent_outputs():
    view = mask_observations(session(noise=6), 10_000, keep=2)
    assert view.count("[output cleared]") == 4


def test_masking_gives_up_recent_outputs_before_user_messages():
    view = mask_observations(session(noise=6), 300, keep=3)
    assert RULE in view and view.count("[output cleared]") > 4


def test_hook_parses_transcript_skips_injected_text_and_respects_cap(tmp_path):
    rows = [
        {"type": "user", "message": {"content": RULE}},
        {"type": "user", "message": {"content": "<system-reminder>not the user</system-reminder>"}},
        {"type": "user", "isMeta": True, "message": {"content": "meta"}},
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": "a", "name": "Bash", "input": {"c": "ls"}}]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "a", "content": "x\n" * 9000}]
            },
        },
        "not json",
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows))
    out = hook.build(path)
    assert RULE in out and "not the user" not in out and "meta" not in out.split("##")[1]
    assert len(out) <= hook.LIMIT_CHARS and str(path) in out


def test_hook_never_raises(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("garbage"))
    hook.main()
    assert capsys.readouterr().out == ""
