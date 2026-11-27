"""The ledger: compaction without a model call.

Rules, each taken from published failure analyses (see README):
1. What the user said is kept verbatim. Paraphrase is where constraints die.
2. Facts are extracted deterministically; a newer value supersedes an older one, visibly.
3. Tool output is reduced to a one-line stub that carries an id.
4. Nothing is destroyed: the archive is append-only and `recall` retrieves any of it.
5. Whatever is left out is declared, so the agent knows to look.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .events import CHARS_PER_TOKEN, Event, render, tokens

HEADER = (
    "CONTEXT LEDGER (earlier history was compacted). User messages below are verbatim and "
    "still binding unless a later one changes them. Facts were extracted automatically and may be "
    "incomplete; treat them as unverified. Anything omitted can be retrieved with recall."
)
# Share of the budget each section may claim, in priority order. Unused budget rolls forward.
SHARES = {"user": 0.40, "facts": 0.22, "notes": 0.16, "recent": 0.14, "tools": 0.08}

_ASSIGN = re.compile(r"\b([A-Za-z][A-Za-z0-9]*(?:[_.][A-Za-z0-9]+)+)\s*(?:=|:)\s*([^\s,;)\]]+)")
_PATH = re.compile(r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z]{1,5})\b")
_ERROR = re.compile(r"^.*\b(?:ERROR|FATAL|Exception|Traceback|[A-Z]\w+Error)\b.*$", re.MULTILINE)
_DECISION = re.compile(
    r"\b(?:decid\w+|going with|chose|choosing|because|root cause|turns? out|turned out|"
    r"instead of|the fix|will use|conclusion)\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[A-Za-z0-9_]{3,}")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fit(lines: Sequence[str], budget: int) -> tuple[list[str], int]:
    """Keep the newest lines that fit in `budget` tokens, in original order."""
    kept: list[str] = []
    used = 0
    for line in reversed(lines):
        cost = tokens(line) + 1
        if used + cost > budget:
            continue
        kept.append(line)
        used += cost
    return kept[::-1], used


class Ledger:
    """Feed it events as they happen; ask for a compacted view at any time.

    State is only ever appended to, so compacting twice cannot compound losses: each view is
    rebuilt from the original events, never from a previous view.
    """

    def __init__(self) -> None:
        self.archive: list[Event] = []

    def extend(self, events: Iterable[Event]) -> None:
        self.archive.extend(events)

    # -- extraction ---------------------------------------------------------------
    def facts(self) -> list[str]:
        values: dict[str, list[tuple[str, int]]] = {}
        paths: dict[str, int] = {}
        errors: dict[str, int] = {}
        for ev in self.archive:
            for key, value in _ASSIGN.findall(ev.text):
                history = values.setdefault(key, [])
                value = value.rstrip(".")
                if not history or history[-1][0] != value:
                    history.append((value, ev.id))
            for path in _PATH.findall(ev.text):
                paths[path] = ev.id
            for line in _ERROR.findall(ev.text):
                errors[_clip(line.strip(), 160)] = ev.id
        # Oldest first, so `_fit` drops the stalest facts. Changed values and errors go last:
        # they are the ones an agent most often gets wrong.
        out = [f"file {p} (#{i})" for p, i in sorted(paths.items(), key=lambda kv: kv[1])]
        stable = [(h[-1][1], k, h) for k, h in values.items() if len(h) == 1]
        out += [f"{k} = {h[-1][0]} (#{i})" for i, k, h in sorted(stable)]
        out += [f"error: {line} (#{i})" for line, i in sorted(errors.items(), key=lambda kv: kv[1])]
        changed = [(h[-1][1], k, h) for k, h in values.items() if len(h) > 1]
        out += [f"{k} = {h[-1][0]} (#{i}; was {h[-2][0]})" for i, k, h in sorted(changed)]
        return out

    def _notes(self) -> list[str]:
        return [
            f"#{ev.id} {_clip(s.strip(), 240)}"
            for ev in self.archive
            if ev.role == "assistant"
            for s in _SENTENCE.split(ev.text)
            if _DECISION.search(s)
        ]

    def _stubs(self) -> list[str]:
        stubs = []
        for ev in self.archive:
            if ev.role != "tool":
                continue
            lines = [x for x in ev.text.splitlines() if x.strip()]
            last = _clip(lines[-1].strip(), 90) if lines else ""
            stubs.append(f"#{ev.id} {ev.name}: {len(lines)} lines, ends: {last}")
        return stubs

    # -- views ----------------------------------------------------------------------
    def compact(self, budget: int) -> str:
        """A context of at most `budget` estimated tokens."""
        sections = {
            "user": (
                "User messages (verbatim)",
                [f"#{e.id} {e.text}" for e in self.archive if e.role == "user"],
            ),
            "facts": ("Facts (latest value wins)", self.facts()),
            "notes": ("Decisions and findings (agent's own words)", self._notes()),
            "recent": ("Most recent events", [_clip(render(e), 600) for e in self.archive[-6:]]),
            "tools": ("Tool log (output removed)", self._stubs()),
        }
        # Reserve room for the header, titles and omission notices before sharing the rest.
        available = max(0, budget - tokens(HEADER) - 30 * len(sections))
        blocks = [HEADER]
        carry = 0
        for key, (title, lines) in sections.items():
            allowance = int(available * SHARES[key]) + carry
            kept, used = _fit(lines, allowance)
            carry = allowance - used
            omitted = len(lines) - len(kept)
            if omitted:
                title += f" [{omitted} older omitted: use recall]"
            if lines:
                blocks.append("\n".join([f"## {title}", *kept]))
        return "\n\n".join(blocks)[: budget * CHARS_PER_TOKEN]

    def recall(self, query: str, budget: int = 600) -> str:
        """Best-matching archived lines (with a little surrounding text) for a search query."""
        wanted = {w.lower() for w in _WORD.findall(query)}
        scored = []
        for ev in self.archive:
            lines = ev.text.splitlines() or [""]
            for i, line in enumerate(lines):
                have = {w.lower() for w in _WORD.findall(f"{ev.name} {line}")}
                hits = sum(any(w in h or h in w for h in have) for w in wanted)
                if hits:
                    window = " | ".join(x.strip() for x in lines[max(0, i - 1) : i + 2])
                    scored.append((-hits, -ev.id, i, f"#{ev.id} {_clip(window, 300)}"))
        kept: list[str] = []
        used = 0
        for *_, text in sorted(scored):
            cost = tokens(text) + 1
            if used + cost > budget:
                break
            kept.append(text)
            used += cost
        return "\n".join(kept) or "no match"
