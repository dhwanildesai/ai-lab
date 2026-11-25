"""Replay a recorded trace offline: no network, no real tools, same answers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .trace import Event, Trace, digest


class DivergenceError(Exception):
    """The agent did something different from the recorded run."""


class Replayer:
    def __init__(self, trace: Trace) -> None:
        self.trace = trace
        self._i = 0

    def _wrap(self, kind: str, name: str) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if self._i >= len(self.trace.events):
                raise DivergenceError(f"extra {kind} call '{name}' beyond end of trace")
            ev: Event = self.trace.events[self._i]
            payload = {"args": list(args), "kwargs": kwargs}
            if (ev.kind, ev.name) != (kind, name):
                raise DivergenceError(
                    f"event {ev.seq}: expected {ev.kind}:{ev.name}, agent called {kind}:{name}"
                )
            if ev.input_hash != digest(payload):
                raise DivergenceError(f"event {ev.seq}: {kind}:{name} called with different input")
            self._i += 1
            if ev.error:
                raise RuntimeError(f"(replayed) {ev.error}")
            return ev.output

        return wrapped

    def tool(self, name: str) -> Callable[..., Any]:
        return self._wrap("tool", name)

    def llm(self, name: str = "llm") -> Callable[..., Any]:
        return self._wrap("llm", name)

    def finished(self) -> bool:
        """True if the agent consumed the whole trace (no missing calls)."""
        return self._i == len(self.trace.events)
