"""Trace data model. A trace is an ordered list of events, stored as JSONL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def canonical(obj: Any) -> str:
    """Stable JSON encoding so equal inputs always hash equally."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=repr)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()[:16]


@dataclass
class Event:
    seq: int
    kind: str  # "llm" or "tool"
    name: str
    input: Any
    input_hash: str
    output: Any = None
    error: str | None = None  # "ExcType: message" if the call raised


@dataclass
class Trace:
    events: list[Event] = field(default_factory=list)

    def save(self, path: str | Path) -> None:
        with open(path, "w") as f:
            f.writelines(json.dumps(asdict(e), default=repr) + "\n" for e in self.events)

    @classmethod
    def load(cls, path: str | Path) -> Trace:
        with open(path) as f:
            return cls([Event(**json.loads(line)) for line in f if line.strip()])

    def tool_sequence(self) -> list[tuple[str, str]]:
        """(tool name, input hash) in call order: the agent's observable behavior."""
        return [(e.name, e.input_hash) for e in self.events if e.kind == "tool"]
