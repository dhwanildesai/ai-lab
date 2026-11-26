"""Cached real-model calls through headless Claude Code (no tools, no settings, scratch cwd)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

CACHE = Path(__file__).parent / "live" / "cache.json"
_lock = threading.Lock()
_cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}


def key(model: str, system: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\0{system}\0{prompt}".encode()).hexdigest()[:24]


def ask(model: str, system: str, prompt: str, offline: bool = False) -> str:
    k = key(model, system, prompt)
    with _lock:
        if k in _cache:
            return _cache[k]
    if offline:
        raise KeyError(f"no cached reply for {k}")
    env = {x: v for x, v in os.environ.items() if x != "ANTHROPIC_API_KEY"}
    cmd = ["claude", "-p", "--output-format", "json", "--model", model, "--tools", "",
           "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence",
           "--system-prompt", system]  # fmt: skip
    cwd = tempfile.mkdtemp(prefix="ledger-scratch-")
    for attempt in range(3):
        try:
            done = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, cwd=cwd, env=env,
                timeout=300, check=True,
            )  # fmt: skip
            reply = json.loads(done.stdout)["result"].strip()
            break
        except (subprocess.SubprocessError, ValueError, KeyError):
            if attempt == 2:
                raise
    with _lock:
        _cache[k] = reply
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(_cache, indent=0, sort_keys=True))
    return reply
