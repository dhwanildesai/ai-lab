"""The unit of agent history, and a rough token estimate."""

from __future__ import annotations

from typing import NamedTuple

CHARS_PER_TOKEN = 4  # estimate only; every strategy is budgeted with the same one


class Event(NamedTuple):
    id: int
    role: str  # "user" | "assistant" | "tool"
    text: str
    name: str = ""  # tool name, or the command that produced a tool result


def render(event: Event) -> str:
    label = f"tool:{event.name}" if event.role == "tool" else event.role
    return f"[#{event.id} {label}] {event.text}"


def tokens(text: str) -> int:
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN
