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

Measured with `pytest`. The benchmark uses a simulated LLM, not a live model; live-model validation is the next step.

## Failure modes
- Non-JSON-serializable values are stored via `repr`, so they replay as strings.
- Hidden nondeterminism outside wrapped calls (clocks, random, env) is not captured.
- Streaming responses are not supported yet.

## Run it
```bash
pip install -e . pytest && pytest
PYTHONPATH=src python examples/demo.py
```
