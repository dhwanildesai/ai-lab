"""The agent loop. A model is any callable: request dict in, reply dict out.

Request: {"phase": "act" | "plan" | "answer", "system": str, "messages": [...], "tools": [...]}
Reply:   {"tool": name, "args": {...}}  or  {"answer": str}  or (plan phase) {"plan": [calls]}

The harness, not the model, decides which tools exist. A call to a tool that was not offered
in this phase is recorded in `blocked` and never executed.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from .defenses import markers, prepare_output, system_prompt
from .scenarios import TOOLS, Scenario

Model = Callable[[dict], dict]


@dataclass
class Transcript:
    calls: list[dict] = field(default_factory=list)  # executed
    blocked: list[dict] = field(default_factory=list)  # refused by the harness
    answer: str = ""
    messages: list[dict] = field(default_factory=list)


def run_episode(
    model: Model,
    scenario: Scenario,
    config: str,
    injection: str | None,
    rng: random.Random,
    max_steps: int = 4,
) -> Transcript:
    mk = markers(config, rng)
    system = system_prompt(config, mk)
    t = Transcript(messages=[{"role": "user", "content": scenario.prompt}])

    def ask(phase: str, tools) -> dict:
        reply = model(
            {"phase": phase, "system": system, "messages": list(t.messages), "tools": list(tools)}
        )
        if not isinstance(reply, dict):
            raise TypeError(f"model reply must be a dict, got {type(reply).__name__}")
        return reply

    def execute(call: dict) -> None:
        name, args = call.get("tool"), call.get("args") or {}
        if name == "send_message":
            out = "Message sent."
        elif name == scenario.tool and args.get("target") == scenario.target:
            out = prepare_output(config, scenario.tool_output(injection), mk)
        else:
            out = "Error: not found."
        t.calls.append({"tool": name, "args": args})
        t.messages += [
            {"role": "assistant", "tool": name, "args": args},
            {"role": "tool", "content": out},
        ]

    if config == "plan_then_execute":
        # The plan is formed from the user's prompt alone, so every call in it is trusted.
        for call in ask("plan", TOOLS).get("plan", [])[:max_steps]:
            if call.get("tool") in TOOLS:
                execute(call)
            else:
                t.blocked.append(call)
        reply = ask("answer", ())
        if "tool" in reply:
            t.blocked.append({"tool": reply["tool"], "args": reply.get("args") or {}})
        t.answer = str(reply.get("answer", ""))
        return t

    for _ in range(max_steps):
        reply = ask("act", TOOLS)
        if "tool" not in reply:
            t.answer = str(reply.get("answer", ""))
            break
        if reply["tool"] in TOOLS:
            execute(reply)
        else:
            t.blocked.append({"tool": reply["tool"], "args": reply.get("args") or {}})
            t.messages.append({"role": "tool", "content": "Error: tool not available."})
    return t
