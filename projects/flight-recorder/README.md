# flight-recorder

> Deterministic record/replay and diffing for LLM agent runs, with zero dependencies.

## Hypothesis
Agent failures are hard to debug because runs are nondeterministic and depend on live LLMs and tools.
If every LLM and tool call is recorded, a run can be **replayed offline with identical behavior**, and
two runs can be **diffed to the first call where they diverge**.

## Design
```
agent code ──► Recorder.llm / Recorder.tool ──► trace.jsonl   (seq, kind, name, input, input_hash, output, error)
agent code ──► Replayer.llm / Replayer.tool ◄── trace.jsonl   (no network, no real tools)
```
- **Wrapping, not patching.** You pass wrapped callables into your agent, so it works with any framework.
- **Input hashing.** Each call stores a hash of its canonicalised input. On replay, a different input is a
  `DivergenceError` at the exact event, which turns a prompt or code change into a regression test.
- **Errors are first-class.** Exceptions are recorded and re-raised on replay.
- **Tradeoff:** replay is strict and sequential. An agent that legitimately reorders parallel tool calls
  will be flagged as divergent. Order-insensitive matching is future work.

## Results
| Check | Outcome |
|---|---|
| Replay of 200 randomized agent runs (seeded nondeterministic LLM) | 200/200 identical output, full trace consumed |
| Changed input, wrong tool, extra call, missing call | each detected (see `tests/`) |
| JSONL save/load round trip | behaviorally identical |

The 200-run benchmark uses a simulated LLM. A real Claude run is recorded and replayed in the example below.

## Example: a real Claude agent run

`examples/real_agent.py` is a small tool-using agent (`list_repos`, `get_repo_stats`, `calculate`)
driven by real Claude (`claude-opus-5-5`, requested via headless Claude Code). The question:
*"Which repo has the most stars per open issue, and what is the ratio?"* The committed trace is
[`examples/traces/claude_agent_run.jsonl`](examples/traces/claude_agent_run.jsonl): **15 events** (7 model calls, 8 tool calls).

| # | Event | Recorded output |
|---|---|---|
| 0, 2, 4, 6 | `llm` | Claude calls `list_repos`, then `get_repo_stats` for each repo |
| 1 | `tool list_repos` | `["alpha-agent", "beta-rag", "gamma-evals"]` |
| 3 / 5 / 7 | `tool get_repo_stats` | 1240 stars / 31 issues, 860 / 9, 410 / 2 |
| 8, 10, 12 | `llm` -> `tool calculate` | Claude delegates arithmetic: `205.0`, `95.5556`, `40.0` |
| 14 | `llm` | *"gamma-evals has the most stars per open issue, with a ratio of 205.00 (410 stars / 2 open issues). It is well ahead of beta-rag at 95.56 and alpha-agent at 40.00."* |

Replaying it needs no network, no API key and no `claude` binary:

```console
$ python examples/real_agent.py replay
Replayed offline (15 events, fully consumed: True)
ANSWER: gamma-evals has the most stars per open issue, with a ratio of 205.00 (410 stars / 2 open issues). ...
Regression caught after prompt edit: event 0: llm:claude-opus-5-5 called with different input
```

The last line is the point: change the agent's system prompt and replay refuses to continue,
naming the first event that differs. `tests/test_committed_claude_trace.py` runs this in CI.
Re-record with `python examples/real_agent.py record` (or `record --api` for the Messages API).

## Failure modes
- Non-JSON-serializable values are stored via `repr`, so they replay as strings.
- Hidden nondeterminism outside wrapped calls (clocks, random, env) is not captured.
- Streaming responses are not supported yet.
- The committed run used a single recording, so it shows replay works on one real run, not that it holds across many.

## Run it
```bash
pip install -e . pytest && pytest
PYTHONPATH=src python examples/demo.py
```
