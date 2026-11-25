# Idea backlog (less-trodden ground)

Chosen to avoid the "chat with your PDF" pile. Each has a measurable claim.

1. **Agent flight recorder**: deterministic record/replay of agent runs (LLM + tool calls) so a failed run can be re-executed offline and diffed. *Claim: replay reproduces 100% of tool-call sequences.*
2. **Tool-description fuzzer**: auto-mutate MCP tool descriptions and measure how selection accuracy changes. *Claim: wording alone shifts accuracy by X points.*
3. **Prompt-injection canary harness**: plant canary instructions in tool outputs and score which agent configs obey them.
4. **Cost-aware model router**: learn from eval results when a small model is good enough; report $/task vs. quality.
5. **Context-rot benchmark**: how does task accuracy decay as irrelevant context grows, per model?
6. **Agent trace → regression test generator**: turn a good production trace into a pytest case automatically.
7. **Semantic diff for prompts**: show behavior differences between two prompt versions over a fixed eval set, not text diffs.
8. **Speculative tool execution**: predict and prefetch the next tool call to cut agent latency.
