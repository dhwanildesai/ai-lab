"""`--cmd` adapter: real Claude picks the tool. JSON on stdin, tool name on stdout.

Answers are cached on disk (examples/live/cache.json), keyed by the exact prompt, so a run is
reproducible and re-running costs nothing. Uses headless Claude Code: no tools, no settings,
empty scratch cwd, subscription auth (ANTHROPIC_API_KEY is removed from the child environment).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MODEL = os.environ.get("FUZZER_MODEL", "claude-haiku-5-5")
CACHE = Path(__file__).parent / "live" / "cache.json"
SYSTEM = (
    "You route a user request to exactly one tool. Reply with ONLY the tool name, "
    "copied exactly from the list. No punctuation, no explanation."
)


def build_prompt(payload: dict) -> str:
    tools = "\n".join(f"- {t['name']}: {t['description']}" for t in payload["tools"])
    return f"Tools:\n{tools}\n\nRequest: {payload['query']}\n\nTool name:"


def key(payload: dict) -> str:
    return hashlib.sha256(f"{MODEL}\n{SYSTEM}\n{build_prompt(payload)}".encode()).hexdigest()[:24]


def load_cache() -> dict:
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))


def ask(payload: dict) -> str:
    """One real model call. Returns the raw reply text."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cmd = ["claude", "-p", "--output-format", "json", "--model", MODEL, "--tools", "",
           "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence",
           "--system-prompt", SYSTEM]  # fmt: skip
    cwd = tempfile.mkdtemp(prefix="fuzzer-scratch-")
    done = subprocess.run(
        cmd, input=build_prompt(payload), capture_output=True, text=True, cwd=cwd, env=env,
        timeout=180, check=True,
    )  # fmt: skip
    return json.loads(done.stdout)["result"].strip()


def answer(payload: dict, cache: dict | None = None) -> str:
    cache = load_cache() if cache is None else cache
    k = key(payload)
    if k not in cache:
        cache[k] = ask(payload)
        save_cache(cache)
    return cache[k]


def main() -> None:
    print(answer(json.load(sys.stdin)))


if __name__ == "__main__":
    main()
