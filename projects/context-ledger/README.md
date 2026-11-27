# context-ledger

> Compact a long agent session without a model call, keep what the user said word for word, and let
> the agent search for anything left out.

**The short answer, from 8 held-out synthetic sessions and real models:** being able to **search the
full history** mattered far more than how the compacted context was written. With search, the ledger,
a model-written structured summary and a hybrid of the two **tied exactly** (98.3% and 99.2%). The
ledger got there with **zero summarization calls**. It did **not** beat a good summary on accuracy, and
without search it was clearly worse.

## Hypothesis
A deterministic, restorable ledger preserves as much usable information after compaction as a
model-written summary. **Verdict: false without search (60.0% vs 72.5%, 42.5% vs 73.3%); a tie with
search.**

## What the research says (and what the design takes from it)
These are the authors' claims, from truncated page reads. I did not reproduce them.

| Finding | Source | Design choice |
|---|---|---|
| Keeping prose verbatim recalled more planted facts than stock summaries (author tests own method) | [Woolford 2026](https://arxiv.org/html/2610.20116) | User messages are never reworded; omissions are declared |
| Summaries drop process rules, and loss compounds across compactions | [Salle et al. 2026](https://arxiv.org/html/2610.31778) | Each view is rebuilt from the archive, never from a previous view |
| A model-free fact digest matched full context on task completion in one setup | [Liu 2026](https://arxiv.org/html/2608.16370) | Deterministic fact extraction |
| No policy dominates; clearing tool output is cheap and strong | [Satish et al. 2026](https://arxiv.org/html/2609.32961) | Tool output becomes one-line stubs |
| Compression should be restorable | [Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) | Append-only archive plus `recall` |
| Structured, merged summaries scored best (vendor's own test) | [Factory](https://factory.ai/news/evaluating-compression) | Used as the strong baseline |

## Design
```
events ──► append-only archive ──┬─► compact(budget): user messages (verbatim) · facts (newest wins,
                                 │     "was X") · decisions · recent events · tool stubs
                                 └─► recall(query): best-matching archived lines
```
- **No model call to compact,** so no summarizer cost or wait, and the same input gives the same output.
- **Budgeted sections** with unused room rolling forward; whatever is dropped is counted in the title.
- **Tradeoff:** extraction is pattern-based. A fact written in plain prose inside tool output is
  invisible until someone searches for it.
- **Tradeoff:** more is left for `recall`, so the agent searches more often than with a summary.

## Results
Each session has 15 questions in six types. Every method gets the same token budget (`full` is the
uncompacted upper bound) and compaction runs repeatedly. `claude-haiku-5-5` answers; summaries are
written by the stronger `claude-sonnet-5-5`, so the baselines are not handicapped. Seeds 100-107 were
not run until the ledger and benchmark code were committed; only call-retry handling changed
afterwards. All 408 model replies are committed.
`+recall` methods may search once per question; **all of them use the same ledger `recall`**.
In the tables, `recalls` counts questions per session that asked for a search (answered together in
one extra model call), and `summ.calls` counts summarizer calls per session.

**Condition A: 1,500-token budget, 3 compactions** (`python examples/bench.py --seeds 100-107 --budget 1500 --rounds 3`)
```console
8 sessions, 15 probes each, budget 1500 est. tokens, 3 compaction rounds. answerer=claude-haiku-5-5 summarizer=claude-sonnet-5-5

method              correct  95% CI        wrong  tokens recalls summ.calls        user rule  updated value    tool output          error  agent finding     unforeseen
full                 100.0%  [100%, 100%]   0.0%   14146     0.0          0             100%           100%           100%           100%           100%           100%
truncate               2.5%  [1%, 5%]       0.0%    1322     0.0          0               0%            19%             0%             0%             0%             0%
mask                  40.0%  [40%, 40%]     0.0%    1110     0.0          0             100%            50%             0%             0%           100%             0%
summary               69.2%  [66%, 72%]     0.0%     722     0.0          3             100%            94%           100%           100%            75%             0%
structured            72.5%  [71%, 73%]     0.0%     808     0.0          3             100%           100%           100%           100%            94%             0%
structured+recall     98.3%  [96%, 100%]    0.0%     808     4.1          3             100%           100%           100%           100%           100%            94%
ledger                60.0%  [56%, 64%]     0.0%    1310     0.0          0             100%           100%            50%           100%            50%             0%
ledger+recall         98.3%  [96%, 100%]    0.0%    1310     6.0          0             100%           100%           100%           100%           100%            94%
hybrid+recall         98.3%  [96%, 100%]    0.0%    1330     4.0          3             100%           100%           100%           100%           100%            94%

paired difference in correct, ledger+recall minus other (95% CI over sessions):
  vs full                -1.7 points  [-4.2, +0.0]
  vs truncate           +95.8 points  [+94.2, +98.3]
  vs mask               +58.3 points  [+55.8, +60.0]
  vs summary            +29.2 points  [+25.8, +33.3]
  vs structured         +25.8 points  [+23.3, +28.3]
  vs structured+recall   +0.0 points  [+0.0, +0.0]
  vs ledger             +38.3 points  [+33.3, +43.3]
  vs hybrid+recall       +0.0 points  [+0.0, +0.0]
```

**Condition B: 700-token budget, 6 compactions** (`... --budget 700 --rounds 6`)
```console
8 sessions, 15 probes each, budget 700 est. tokens, 6 compaction rounds. answerer=claude-haiku-5-5 summarizer=claude-sonnet-5-5

method              correct  95% CI        wrong  tokens recalls summ.calls        user rule  updated value    tool output          error  agent finding     unforeseen
full                 100.0%  [100%, 100%]   0.0%   25835     0.0          0             100%           100%           100%           100%           100%           100%
truncate               0.8%  [0%, 2%]       0.0%     471     0.0          0               0%             6%             0%             0%             0%             0%
mask                   9.2%  [8%, 12%]      0.0%     631     0.0          0               0%            50%             0%             0%            19%             0%
summary               70.8%  [68%, 72%]     0.0%     650     0.0          6             100%           100%           100%           100%            81%             0%
structured            73.3%  [73%, 73%]     0.0%     689     0.0          6             100%           100%           100%           100%           100%             0%
structured+recall     99.2%  [98%, 100%]    0.0%     689     4.0          6             100%           100%           100%           100%           100%            97%
ledger                42.5%  [37%, 49%]     0.0%     568     0.0          0             100%           100%             6%            12%            50%             0%
ledger+recall         99.2%  [98%, 100%]    0.0%     568     8.6          0             100%           100%           100%           100%           100%            97%
hybrid+recall         99.2%  [98%, 100%]    0.0%     605     5.0          6             100%           100%           100%           100%           100%            97%

paired difference in correct, ledger+recall minus other (95% CI over sessions):
  vs full                -0.8 points  [-2.5, +0.0]
  vs truncate           +98.3 points  [+95.8, +100.0]
  vs mask               +90.0 points  [+87.5, +92.5]
  vs summary            +28.3 points  [+25.0, +30.8]
  vs structured         +25.8 points  [+24.2, +26.7]
  vs structured+recall   +0.0 points  [+0.0, +0.0]
  vs ledger             +56.7 points  [+50.0, +62.5]
  vs hybrid+recall       +0.0 points  [+0.0, +0.0]
```

### What this shows
- **Search is the large effect.** Adding it to the structured summary took it from 72.5% to 98.3% (A)
  and from 73.3% to 99.2% (B).
- **That gap is almost entirely the `unforeseen` questions** (ordinary log lines picked afterwards),
  which no summary kept: 0% without search. On the other 11 question types the structured summary
  alone scored 98.9% (87/88, A) and 100% (88/88, B). If your agent never needs such detail, a good
  summary is enough.
- **Ledger versus summary, both with search:** identical scores. The ledger saves 3 or 6 Sonnet calls
  per session, but asks for more searches (6.0 vs 4.1 in A, 8.6 vs 4.0 in B), which adds retrieved text
  (up to 200 estimated tokens each). Its context was larger in A (1,310 vs 808) and smaller in B
  (568 vs 689). Total cost and latency were **not** measured.
- **The hybrid added nothing measurable** over either part.
- **The ledger alone degrades badly when squeezed:** in B it scored 6% on tool-output questions and 12%
  on errors. Probably look-alike values and
  errors from noise logs crowd the small facts section; that cause was not isolated.
- **Truncation and observation masking lost most early information** in these sessions, where planted
  facts are old and tool output is bulky. Masking did keep user rules in A.

## Failure modes and threats to validity
- **Synthetic sessions, one author.** I wrote the method, the session generator and the questions.
  I changed the benchmark several times while looking at development seeds (harder questions, more
  rounds, the hybrid). The `unforeseen` type favors search by design.
- **Easy questions.** Full context scores 100%, answers are short exact strings, and phrasing pools are
  small, so the confidence intervals understate how results vary on real work.
- **Recall is optimistic here.** All searches are batched into one extra call. A real agent spends a
  tool turn per search and may not realize it needs one. Some questions were missed by all three
  search methods, a limit of the shared keyword search.
- **No comparison** with Claude Code's own compaction or any vendor compaction API.
- One answering model, one summarizer, English only, tokens estimated as characters / 4. The exact
  model served by the headless CLI could not be independently confirmed.

## Use it in Claude Code (optional, experimental)
`hooks/after_compact.py` is a `SessionStart` hook for the `compact` matcher. After a compaction it adds
a ledger (at most 10,000 characters) next to Claude Code's own summary, with the transcript path for
looking up older detail. It makes no model or network calls and writes nothing. Add to
`~/.claude/settings.json`, using your own path:

```json
{"hooks": {"SessionStart": [{"matcher": "compact", "hooks": [
  {"type": "command", "command": "python3 /path/to/ai-lab/projects/context-ledger/hooks/after_compact.py"}
]}]}}
```
**Status:** unit-tested and run once on a real 5 MB transcript (0.04 s, 8,242 characters, all 19 parsed
user messages kept). **Not** tested inside a live compaction, and **not** covered by the benchmark.
The transcript format is undocumented and may change. It adds context rather than replacing the summary.

## Run it
```bash
pip install pytest && pytest                                             # includes an offline replay
python examples/bench.py --seeds 100-107 --budget 1500 --rounds 3 --offline   # free
python examples/bench.py --seeds 200-207                                 # new sessions: real model calls
```
