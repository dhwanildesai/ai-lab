"""Embed the committed trace into template.html -> index.html (no fetch needed, works from file://)."""

import json
from pathlib import Path

here = Path(__file__).parent
trace = here.parents[1] / "projects/flight-recorder/examples/traces/claude_agent_run.jsonl"
events = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
blob = json.dumps(events).replace("</", "<\\/")
(here / "index.html").write_text((here / "template.html").read_text().replace("__TRACE__", blob))
print(f"wrote index.html with {len(events)} events")
