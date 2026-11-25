# ai-lab

Small, rigorous experiments in AI agents and LLM infrastructure. Each project in `projects/` is self-contained and follows the same shape:

| Section | Question it answers |
|---|---|
| **Hypothesis** | What am I testing? |
| **Design** | Architecture and the tradeoffs I chose |
| **Results** | What I measured (evals, latency, cost) |
| **Failure modes** | Where it breaks, honestly |
| **Run it** | One command to reproduce |

## Projects
<!-- INDEX:START -->
| Project | Claim |
|---|---|
| [flight-recorder](projects/flight-recorder) ([live demo](https://dhwanildesai.github.io/ai-lab/flight-recorder/)) | Record/replay and diff LLM agent runs deterministically, offline |
| [tool-description-fuzzer](projects/tool-description-fuzzer) | Wording shifts tool-selection accuracy by up to 31 points on simulated selectors, but not at all on Claude Haiku 5.5 (768 real calls; ceiling effect) |
<!-- INDEX:END -->

## Conventions
- Python 3.12, `uv`, `ruff`, `pytest`, type hints required.
- Every project ships with tests and passes CI before merge.
- No secrets in the repo. Config via env vars; see each `.env.example`.
- Start a new project: `make new name=my-idea`.
