# Idea backlog (less-trodden ground)

The daily agent picks the first unchecked item and checks it off in its PR.

Chosen to avoid the "chat with your PDF" pile. Each has a measurable claim.

- [x] **Agent flight recorder**: deterministic record/replay of agent runs (LLM + tool calls) so a failed run can be re-executed offline and diffed. *Claim: replay reproduces 100% of tool-call sequences.*
- [x] **Tool-description fuzzer**: auto-mutate MCP tool descriptions and measure how selection accuracy changes. *Claim: wording alone shifts accuracy by X points.* Result: yes on simulated selectors (up to 31 points); none on Claude Haiku 5.5 with self-descriptive tool names (ceiling effect). Next: opaque names and ambiguous tasks.
- [x] **Prompt-injection canary harness**: plant canary instructions in tool outputs and score which agent configs obey them. Result (simulated agents only): literal canaries score a quote-only agent as 100% compromised, split canaries 0%; plan-then-execute stops action canaries, not content canaries. Next: run `--cmd` against a real model.
- [ ] **Cost-aware model router**: learn from eval results when a small model is good enough; report $/task vs. quality.
- [ ] **Context-rot benchmark**: how does task accuracy decay as irrelevant context grows, per model?
- [ ] **Agent trace → regression test generator**: turn a good production trace into a pytest case automatically.
- [ ] **Semantic diff for prompts**: show behavior differences between two prompt versions over a fixed eval set, not text diffs.
- [ ] **Speculative tool execution**: predict and prefetch the next tool call to cut agent latency.
- [x] **Restorable context compaction**: compact without a model call and recall on demand. *Claim: matches model-written summaries.* Result: ties with history search, loses without it (synthetic sessions).
