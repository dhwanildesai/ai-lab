"""The live demo page embeds the trace. Fail CI if it drifts from the committed trace."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRACE = ROOT / "projects/flight-recorder/examples/traces/claude_agent_run.jsonl"
PAGE = ROOT / "docs/flight-recorder/index.html"


def test_demo_page_embeds_current_trace():
    events = [json.loads(line) for line in TRACE.read_text().splitlines() if line.strip()]
    embedded = json.dumps(events).replace("</", "<\\/")
    assert embedded in PAGE.read_text(), "run: python docs/flight-recorder/build.py"
