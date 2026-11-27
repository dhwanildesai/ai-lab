"""Baselines that need no model. The model-written ones live in examples/ (they cost calls)."""

from __future__ import annotations

from collections.abc import Sequence

from .events import CHARS_PER_TOKEN, Event, render, tokens


def truncate(events: Sequence[Event], budget: int) -> str:
    """Sliding window: the newest whole events that fit."""
    kept: list[str] = []
    used = 0
    for ev in reversed(events):
        text = render(ev)
        cost = tokens(text) + 1
        if used + cost > budget:
            break
        kept.append(text)
        used += cost
    if not kept and events:
        return render(events[-1])[-budget * CHARS_PER_TOKEN :]
    return "\n".join(kept[::-1])


def mask_observations(events: Sequence[Event], budget: int, keep: int = 3) -> str:
    """Keep up to `keep` recent tool outputs (fewer if they do not fit), mask the rest.

    If it is still over budget with every output masked, the oldest events are truncated.
    """
    tool_ids = [e.id for e in events if e.role == "tool"]
    for k in range(keep, -1, -1):
        recent = set(tool_ids[-k:]) if k else set()
        masked = [
            e._replace(text="[output cleared]") if e.role == "tool" and e.id not in recent else e
            for e in events
        ]
        if sum(tokens(render(e)) + 1 for e in masked) <= budget:
            break
    return truncate(masked, budget)
