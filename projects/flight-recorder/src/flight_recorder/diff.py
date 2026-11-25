"""Find where two runs of an agent first part ways."""

from __future__ import annotations

from dataclasses import dataclass

from .trace import Trace


@dataclass
class Divergence:
    index: int
    reason: str


def diff_traces(a: Trace, b: Trace) -> Divergence | None:
    """Return the first divergence, or None if the traces are behaviorally identical."""
    for i, (x, y) in enumerate(zip(a.events, b.events)):
        if (x.kind, x.name) != (y.kind, y.name):
            return Divergence(i, f"call differs: {x.kind}:{x.name} vs {y.kind}:{y.name}")
        if x.input_hash != y.input_hash:
            return Divergence(i, f"{x.kind}:{x.name} input differs")
        if x.output != y.output or x.error != y.error:
            return Divergence(i, f"{x.kind}:{x.name} output differs")
    if len(a.events) != len(b.events):
        return Divergence(min(len(a.events), len(b.events)), "one trace is longer")
    return None
