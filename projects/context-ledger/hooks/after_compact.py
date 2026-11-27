#!/usr/bin/env python3
"""Claude Code `SessionStart` (matcher: compact) hook: re-inject a ledger after compaction.

Reads the hook JSON on stdin, rebuilds a ledger from the session transcript and prints it, so
Claude Code adds it to context alongside its own summary. No model calls, no network, no writes.
The transcript format is undocumented, so parsing is defensive and failure prints nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from context_ledger import Event, Ledger

LIMIT_CHARS = 10_000  # documented cap for hook output
BUDGET_TOKENS = 2_200  # leaves headroom under the cap for the trailing recall note
# Harness-injected blocks that arrive as user messages. Anything else, pasted text included,
# is the user's and is kept.
INJECTED = ("<system-reminder", "<command-", "<local-command", "<task-notification")


def _text(block) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, list):
        return "\n".join(_text(b) for b in block)
    if isinstance(block, dict) and block.get("type") == "text":
        return str(block.get("text", ""))
    return ""


def parse_transcript(lines) -> list[Event]:
    events: list[Event] = []
    tool_names: dict[str, str] = {}
    for line in lines:
        try:
            row = json.loads(line)
            if row.get("isSidechain") or row.get("isMeta") or row.get("isCompactSummary"):
                continue
            role = row.get("type")
            content = row["message"]["content"]
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if role not in ("user", "assistant"):
            continue
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                text = str(b.get("text", "")).strip()
                if text and not (role == "user" and text.startswith(INJECTED)):
                    events.append(Event(len(events) + 1, role, text))
            elif b.get("type") == "tool_use":
                arg = json.dumps(b.get("input", {}))[:80]
                tool_names[b.get("id", "")] = f"{b.get('name', 'tool')} {arg}"
            elif b.get("type") == "tool_result":
                name = tool_names.get(b.get("tool_use_id", ""), "tool")
                events.append(Event(len(events) + 1, "tool", _text(b.get("content")), name))
    return events


def build(transcript: Path) -> str:
    with transcript.open(encoding="utf-8", errors="replace") as handle:
        events = parse_transcript(handle)
    if not events:
        return ""
    ledger = Ledger()
    ledger.extend(events)
    note = f"\n\nTo recall omitted detail, search the full transcript: {transcript}"
    return ledger.compact(BUDGET_TOKENS)[: LIMIT_CHARS - len(note)] + note


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        print(build(Path(payload["transcript_path"])), end="")
    except Exception as exc:  # noqa: BLE001 - a hook must never break the session
        print(f"context-ledger hook skipped: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
