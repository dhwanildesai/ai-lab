"""Description mutations. Each is `f(tool, registry, rng) -> new description`.

Names are never touched, so any change in selection is due to the description alone.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Sequence
from re import Match

from .registry import Tool

Mutation = Callable[[Tool, Sequence[Tool], random.Random], str]

SYNONYMS = {
    "add": "insert",
    "book": "reserve",
    "change": "modify",
    "chart": "figure",
    "check": "inspect",
    "contents": "body",
    "count": "tally",
    "download": "retrieve",
    "draw": "render",
    "email": "mail",
    "execute": "perform",
    "find": "discover",
    "locate": "pinpoint",
    "look": "glance",
    "meeting": "appointment",
    "meetings": "appointments",
    "message": "note",
    "messages": "notes",
    "move": "shift",
    "open": "view",
    "page": "document",
    "plot": "graph",
    "query": "request",
    "reply": "respond",
    "schedule": "arrange",
    "search": "scan",
    "send": "dispatch",
    "show": "display",
    "string": "literal",
    "text": "prose",
    "write": "compose",
}
BOILERPLATE = (
    "This tool is part of the productivity suite and is provided to help the assistant "
    "complete requests from the user in a safe and reliable way."
)


def sentences(text: str) -> list[str]:
    return re.split(r"(?<=\.)\s+", text.strip())


def identity(tool: Tool, _registry: Sequence[Tool], _rng: random.Random) -> str:
    """A/A control: must show exactly zero effect."""
    return tool.description


def reorder(tool: Tool, _registry: Sequence[Tool], rng: random.Random) -> str:
    """Shuffle sentences; identical bag of words, so a null for order-blind selectors."""
    parts = sentences(tool.description)
    rng.shuffle(parts)
    return " ".join(parts)


def synonyms(tool: Tool, _registry: Sequence[Tool], rng: random.Random) -> str:
    """Replace each known word with a near-synonym with probability 0.5."""

    def swap(match: Match[str]) -> str:
        word = match.group(0)
        new = SYNONYMS.get(word.lower())
        if new is None or rng.random() >= 0.5:
            return word
        return new.capitalize() if word[0].isupper() else new

    return re.sub(r"[A-Za-z]+", swap, tool.description)


def first_sentence(tool: Tool, _registry: Sequence[Tool], _rng: random.Random) -> str:
    return sentences(tool.description)[0]


def drop_negative(tool: Tool, _registry: Sequence[Tool], _rng: random.Random) -> str:
    """Remove "Do not use ..." guidance."""
    return " ".join(s for s in sentences(tool.description) if not s.startswith("Do not"))


def boilerplate(tool: Tool, _registry: Sequence[Tool], _rng: random.Random) -> str:
    return f"{BOILERPLATE} {tool.description}"


def typos(tool: Tool, _registry: Sequence[Tool], rng: random.Random) -> str:
    """Swap two adjacent inner letters in about 20% of words of five or more letters."""

    def scramble(match: Match[str]) -> str:
        word = match.group(0)
        if rng.random() >= 0.2:
            return word
        i = rng.randrange(1, len(word) - 2)
        return word[:i] + word[i + 1] + word[i] + word[i + 2 :]

    return re.sub(r"[A-Za-z]{5,}", scramble, tool.description)


def stuffing(tool: Tool, registry: Sequence[Tool], rng: random.Random) -> str:
    """Append 12 words taken from *other* tools. Sees the registry, never the tasks."""
    vocabulary = sorted(
        {
            word
            for other in registry
            if other.name != tool.name
            for word in re.findall(r"[a-z]{4,}", sentences(other.description)[0].lower())
        }
    )
    extra = rng.sample(vocabulary, min(12, len(vocabulary)))
    return f"{tool.description} Also handles: {', '.join(extra)}."


MUTATIONS: dict[str, Mutation] = {
    f.__name__: f
    for f in (
        identity,
        reorder,
        synonyms,
        first_sentence,
        drop_negative,
        boilerplate,
        typos,
        stuffing,
    )
}


def mutate(registry: Sequence[Tool], name: str, seed: int, only: str | None = None) -> list[Tool]:
    """Apply a mutation to every tool, or just to `only`. Reproducible per (name, tool, seed)."""
    if only is not None and only not in {t.name for t in registry}:
        raise ValueError(f"unknown tool: {only}")
    fn = MUTATIONS[name]
    out = []
    for tool in registry:
        if only in (None, tool.name):
            # String seeds are hashed with SHA-512, so PYTHONHASHSEED does not matter.
            rng = random.Random(f"{name}/{tool.name}/{seed}")
            tool = tool._replace(description=fn(tool, registry, rng))
        out.append(tool)
    return out
