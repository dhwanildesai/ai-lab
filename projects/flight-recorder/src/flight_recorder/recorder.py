"""Record every LLM and tool call an agent makes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .trace import Event, Trace, digest


class Recorder:
    def __init__(self) -> None:
        self.trace = Trace()

    def _wrap(self, kind: str, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            payload = {"args": list(args), "kwargs": kwargs}
            ev = Event(len(self.trace.events), kind, name, payload, digest(payload))
            self.trace.events.append(ev)  # append first so seq order = call order
            try:
                ev.output = fn(*args, **kwargs)
            except Exception as exc:
                ev.error = f"{type(exc).__name__}: {exc}"
                raise
            return ev.output

        return wrapped

    def tool(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        return self._wrap("tool", name, fn)

    def llm(self, fn: Callable[..., Any], name: str = "llm") -> Callable[..., Any]:
        return self._wrap("llm", name, fn)
