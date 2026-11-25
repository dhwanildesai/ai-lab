# Idea backlog (less-trodden ground)

The daily agent picks the first unchecked item and checks it off in its PR.

Chosen to avoid the "chat with your PDF" pile. Each has a measurable claim.

- [x] **Agent flight recorder**: deterministic record/replay of agent runs (LLM + tool calls) so a failed run can be re-executed offline and diffed. *Claim: replay reproduces 100% of tool-call sequences.*
- [x] **Tool-description fuzzer**: auto-mutate MCP tool descriptions and measure how selection accuracy changes. *Claim: wording alone shifts accuracy by X points.*
- [ ] **Prompt-injection canary harness**: plant canary instructions in tool outputs and score which agent configs obey them.
- [ ] **Cost-aware model router**: learn from eval results when a small model is good enough; report $/task vs. quality.
- [ ] **Context-rot benchmark**: how does task accuracy decay as irrelevant context grows, per model?
- [ ] **Agent trace → regression test generator**: turn a good production trace into a pytest case automatically.
- [ ] **Semantic diff for prompts**: show behavior differences between two prompt versions over a fixed eval set, not text diffs.
- [ ] **Speculative tool execution**: predict and prefetch the next tool call to cut agent latency.
