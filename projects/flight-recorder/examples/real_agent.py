"""Record a real Claude agent run, replay it offline, and catch a regression.

    python examples/real_agent.py record        # real Claude via the `claude` CLI (headless)
    python examples/real_agent.py record --api  # real Claude via the Messages API (needs credits)
    python examples/real_agent.py replay   # offline: no network, no API key

The agent answers a question using two deterministic tools. Only the model call is
nondeterministic, which is exactly what the recorder pins down.
"""

import ast
import json
import operator
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from flight_recorder import DivergenceError, Recorder, Replayer, Trace

TRACE = Path(__file__).parent / "traces" / "claude_agent_run.jsonl"
MODEL = "claude-opus-5-5"
QUESTION = (
    "Among the repos in the database, which has the most stars per open issue, "
    "and what is that ratio to 2 decimals?"
)
SYSTEM = (
    "You answer questions about GitHub repos. Use list_repos and get_repo_stats to fetch "
    "data and calculate for arithmetic. Never do arithmetic in your head. Keep the final "
    "answer to two sentences."
)

REPOS = {
    "alpha-agent": {"stars": 1240, "open_issues": 31},
    "beta-rag": {"stars": 860, "open_issues": 9},
    "gamma-evals": {"stars": 410, "open_issues": 2},
}

TOOLS = [
    {
        "name": "list_repos",
        "description": "List the names of all repos in the database.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_repo_stats",
        "description": "Get stars and open issues for one repo by name.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calculate",
        "description": "Evaluate an arithmetic expression such as '860 / 9'.",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
]

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    raise ValueError("unsupported expression")


def calculate(expression: str) -> str:
    return str(round(_eval(ast.parse(expression, mode="eval").body), 4))


def list_repos() -> str:
    return json.dumps(sorted(REPOS))


def get_repo_stats(name: str) -> str:
    return json.dumps(REPOS.get(name, {"error": f"unknown repo {name}"}))


def run_agent(llm, tools: dict, question: str, system: str = SYSTEM) -> str:
    """Manual Messages-API tool loop. Works on plain dicts so traces are JSON."""
    messages = [{"role": "user", "content": question}]
    for _ in range(10):
        reply = llm(system=system, messages=messages)
        messages.append({"role": "assistant", "content": reply["content"]})
        if reply["stop_reason"] != "tool_use":
            return "".join(b["text"] for b in reply["content"] if b["type"] == "text")
        results = []
        for block in reply["content"]:
            if block["type"] == "tool_use":
                out = tools[block["name"]](**block["input"])
                results.append({"type": "tool_result", "tool_use_id": block["id"], "content": out})
        messages.append({"role": "user", "content": results})
    return "step limit reached"


def make_real_llm():
    import anthropic

    client = anthropic.Anthropic()

    def llm(system: str, messages: list) -> dict:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=system,
            tools=TOOLS,
            messages=messages,
            output_config={"effort": "low"},
        )
        return {
            "stop_reason": resp.stop_reason,
            "content": [b.model_dump(exclude_none=True) for b in resp.content],
            "usage": {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens},
        }

    return llm


PROTOCOL = (
    "\n\nYou can call these tools: list_repos(), get_repo_stats(name), calculate(expression). "
    "Reply with EXACTLY ONE JSON object and nothing else. To call a tool: "
    '{"tool": "<name>", "input": {...}}. To finish: {"final": "<answer>"}. '
    "One tool call per reply."
)


def _render(messages: list) -> str:
    lines = []
    for m in messages:
        if isinstance(m["content"], str):
            lines.append(f"[{m['role']}] {m['content']}")
            continue
        for b in m["content"]:
            if b["type"] == "text":
                lines.append(f"[assistant] {b['text']}")
            elif b["type"] == "tool_use":
                lines.append(
                    f"[assistant tool call] {json.dumps({'tool': b['name'], 'input': b['input']})}"
                )
            elif b["type"] == "tool_result":
                lines.append(f"[tool result] {b['content']}")
    return "\n".join(lines) + "\n[assistant]"


def make_cli_llm():
    """Real Claude through headless Claude Code: no tools, no settings, empty scratch cwd."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cwd = tempfile.mkdtemp(prefix="fr-scratch-")

    def llm(system: str, messages: list) -> dict:
        cmd = [
            "claude",
            "-p",
            "--output-format",
            "json",
            "--model",
            MODEL,
            "--tools",
            "",
            "--setting-sources",
            "",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--system-prompt",
            system + PROTOCOL,
        ]
        out = subprocess.run(
            cmd,
            check=False,
            input=_render(messages),
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=300,
        )
        if out.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {out.stderr[-300:] or out.stdout[-300:]}")
        text = json.loads(out.stdout)["result"].strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        action = json.loads(text)
        if "tool" in action:
            n = sum(
                1
                for m in messages
                if not isinstance(m["content"], str)
                for b in m["content"]
                if b["type"] == "tool_use"
            )
            block = {
                "type": "tool_use",
                "id": f"toolu_{n + 1}",
                "name": action["tool"],
                "input": action.get("input", {}),
            }
            return {"stop_reason": "tool_use", "content": [block]}
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": action["final"]}]}

    return llm


def main(mode: str, backend: str = "cli") -> None:
    if mode == "record":
        rec = Recorder()
        tools = {
            "list_repos": rec.tool("list_repos", list_repos),
            "get_repo_stats": rec.tool("get_repo_stats", get_repo_stats),
            "calculate": rec.tool("calculate", calculate),
        }
        answer = run_agent(
            rec.llm(make_real_llm() if backend == "api" else make_cli_llm(), name=MODEL),
            tools,
            QUESTION,
        )
        rec.trace.save(TRACE)
        print(f"Recorded {len(rec.trace.events)} events -> {TRACE}\nANSWER: {answer}")
        return

    trace = Trace.load(TRACE)
    rp = Replayer(trace)
    tools = {n: rp.tool(n) for n in ("list_repos", "get_repo_stats", "calculate")}
    answer = run_agent(rp.llm(MODEL), tools, QUESTION)
    print(f"Replayed offline ({len(trace.events)} events, fully consumed: {rp.finished()})")
    print(f"ANSWER: {answer}")

    rp2 = Replayer(trace)  # simulate a prompt change in the agent code
    tools2 = {n: rp2.tool(n) for n in ("list_repos", "get_repo_stats", "calculate")}
    try:
        run_agent(rp2.llm(MODEL), tools2, QUESTION, system=SYSTEM + " Be extremely verbose.")
    except DivergenceError as e:
        print(f"Regression caught after prompt edit: {e}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "replay", "api" if "--api" in sys.argv else "cli")
