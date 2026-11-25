# tool-description-fuzzer

> Mutate tool descriptions, hold everything else fixed, and measure how far tool selection moves, on simulated selectors and on real Claude.

**Two result sets, kept separate.** The simulated results (two lexical selectors) show the harness
detects wording effects. The **real-model results (Claude Haiku 5.5, 768 live calls) show no effect at
all on this benchmark**: 100% accuracy and 0% flips under every mutation. The likely reason is a
ceiling effect, not robustness; see [Real model](#real-model-claude-haiku-55).

## Hypothesis
Description wording alone, with tool names and tasks held fixed, changes selection accuracy by a
measurable number of points. Accuracy by itself may also understate the change, because
newly right and newly wrong choices cancel out.

## Design
```
registry (12 tools) ──► mutate(name, seed) ──► selector(query, tools) ──► paired stats per task
tasks (48, labelled) ─────────────────────────────▲
```
- **Eight mutations.** `identity` (A/A control), `reorder` sentences, `synonyms`, `first_sentence` only,
  `drop_negative` ("Do not use ..."), `boilerplate` prefix, `typos`, and keyword `stuffing` from other
  tools. Stuffing sees the registry but never the tasks.
- **Two blast radii.** Mutate all tools at once, or one tool at a time, as a single third-party
  server could. The second reports how many tasks the edited tool *steals* from correct tools.
- **Two selectors with different blind spots.** BM25 ignores word order, so `reorder` must be exactly
  null for it. The lead-biased selector halves a word's weight every 10 tokens, so `reorder` must not be.
- **The task is the statistical unit.** Deltas are averaged over seeds first, then bootstrapped over
  the 48 tasks, with a sign-flip test Holm-corrected across 7 mutations. Treating 20 seeds x 48 tasks
  as 960 samples would make the intervals far too narrow.
- **Flips next to accuracy.** A flip is any change of chosen tool, right or wrong.
- **Tradeoff:** lexical selectors are free, exact and reproducible, but their sensitivity to wording
  is partly built in. They validate the harness; they do not predict a model.
- **Tradeoff:** the simulated selectors are deterministic, so they need no recording. For the live
  model, every reply is cached on disk (`examples/live/cache.json`, keyed by the exact prompt), the
  same record-once idea as flight-recorder, so the real run is reproducible offline.

## Results
Simulated selectors, 12 tools, 48 tasks, 20 seeds. Python 3.9. Real output of
`python examples/demo.py`:

```console
12 tools, 48 tasks, 20 seeds per mutation

== bm25 (simulated): baseline accuracy 77.1%
all tools mutated    acc   delta  95% CI (points)  p_holm  flips
  identity         77.1%    +0.0  [+0.0, +0.0]      1.000   0.0%
  reorder          77.1%    +0.0  [+0.0, +0.0]      1.000   0.0%
  synonyms         62.0%   -15.1  [-21.9, -9.3]     0.003  16.2%
  first_sentence   45.8%   -31.2  [-43.8, -18.8]    0.003  41.7%
  drop_negative    79.2%    +2.1  [+0.0, +6.2]      1.000   8.3%
  boilerplate      77.1%    +0.0  [-6.2, +6.2]      1.000   6.2%
  typos            69.9%    -7.2  [-10.5, -4.3]     0.003   8.1%
  stuffing         59.9%   -17.2  [-26.1, -9.0]     0.003  21.0%
one tool mutated   own recall       stolen from others
  identity         77.1% -> 77.1%        0.0%
  reorder          77.1% -> 77.1%        0.0%
  synonyms         77.1% -> 57.9%        0.0%
  first_sentence   77.1% -> 45.8%        0.0%
  drop_negative    77.1% -> 79.2%        0.7%
  boilerplate      77.1% -> 81.2%        3.7%
  typos            77.1% -> 69.3%        0.0%
  stuffing         77.1% -> 69.2%        0.6%

== lead-biased (simulated): baseline accuracy 70.8%
all tools mutated    acc   delta  95% CI (points)  p_holm  flips
  identity         70.8%    +0.0  [+0.0, +0.0]      1.000   0.0%
  reorder          66.0%    -4.8  [-11.2, +1.3]     0.510  23.8%
  synonyms         55.5%   -15.3  [-22.4, -9.1]     0.003  19.7%
  first_sentence   41.7%   -29.2  [-41.7, -16.7]    0.003  37.5%
  drop_negative    70.8%    +0.0  [+0.0, +0.0]      1.000   4.2%
  boilerplate      64.6%    -6.2  [-14.6, +2.1]     0.748  18.8%
  typos            63.9%    -7.0  [-10.5, -4.0]     0.003   7.8%
  stuffing         65.8%    -5.0  [-10.6, -0.4]     0.510   9.7%
one tool mutated   own recall       stolen from others
  identity         70.8% -> 70.8%        0.0%
  reorder          70.8% -> 60.6%        0.1%
  synonyms         70.8% -> 52.7%        0.0%
  first_sentence   70.8% -> 39.6%        0.0%
  drop_negative    70.8% -> 70.8%        0.0%
  boilerplate      70.8% -> 37.5%        5.9%
  typos            70.8% -> 63.6%        0.0%
  stuffing         70.8% -> 70.8%        0.0%
```

What this does and does not show (all simulated):
- **Wording moved accuracy by up to 31.2 points** (BM25, `first_sentence`). Synonyms, truncation and
  typos are significant after correction on both selectors.
- **Flips catch what accuracy misses.** Under BM25, `boilerplate` has a delta of +0.0 but changes 6.2%
  of choices. Lead-biased `reorder` is not significant on accuracy (p=0.510) but flips 23.8%.
- **Stuffing is a poor attack here.** A single stuffed tool steals 0.6% (BM25) or 0.0% of tasks; under
  BM25 it loses 7.9 points of its own recall. It hurts BM25 when *every* tool does it (-17.2).
- **Not significant:** `drop_negative`, `boilerplate` and `reorder` on both selectors, and
  lead-biased `stuffing` after correction even though its uncorrected interval excludes zero.

## Real model (Claude Haiku 5.5)
Same 12 tools, 48 tasks, 3 seeds per mutation, run through the `--cmd` adapter
(`examples/claude_selector.py`) against `claude-haiku-5-5` via headless Claude Code (no tools, no
settings, empty scratch directory). Command and raw output: `python examples/live_run.py --seeds 3`,
[`examples/live/results.txt`](examples/live/results.txt). **768 unique model calls, 0 invalid replies.**
Tool order was held fixed, so position bias is not controlled.

```console
== claude-haiku-5-5 (REAL): baseline accuracy 100.0%
all tools mutated    acc   delta  95% CI (points)  p_holm  flips
  identity        100.0%    +0.0  [+0.0, +0.0]      1.000   0.0%
  reorder         100.0%    +0.0  [+0.0, +0.0]      1.000   0.0%
  synonyms        100.0%    +0.0  [+0.0, +0.0]      1.000   0.0%
  first_sentence  100.0%    +0.0  [+0.0, +0.0]      1.000   0.0%
  drop_negative   100.0%    +0.0  [+0.0, +0.0]      1.000   0.0%
  boilerplate     100.0%    +0.0  [+0.0, +0.0]      1.000   0.0%
  typos           100.0%    +0.0  [+0.0, +0.0]      1.000   0.0%
  stuffing        100.0%    +0.0  [+0.0, +0.0]      1.000   0.0%
```

What this shows:
- **The `--cmd` path works with a real model.** Every reply was a valid tool name.
- **The simulated selectors did not predict this model.** They lost 15 to 31 points under synonyms,
  truncation and typos. Haiku lost nothing, and changed zero of its 1,152 mutated choices (48 tasks x 8
  mutations x 3 seeds, with `identity` included), so it also did not flip while staying correct.
- **This is a ceiling effect, not proof that wording never matters.** Baseline accuracy is 100%, so there
  is no room to fall, and tool *names* are never mutated. Names like `search_files`, `grep_text` and
  `run_sql` give the answer away, so the model can ignore the descriptions. The benchmark cannot detect
  sensitivity in a model that can route from names alone.
- **Not shown:** that this holds for other models, harder or ambiguous tasks, larger registries (12 tools
  is small), opaque tool names, or other tool orderings.

## Failure modes
- **Not an LLM.** A lexical selector breaks on synonyms by construction. A real model may well not.
  None of these effect sizes should be quoted for a model.
- The fixture was written by the same author as the mutations: 12 tools, 48 tasks, some labels
  arguable ("Find every path that matches test_*.py"). Intervals cover task sampling, not author bias.
- Lexical selectors get credit for "Do not use to X" as if it were "use to X", so `drop_negative`
  measures token removal, not whether negation is understood.
- There is no stop-word list, so boilerplate probably "steals" through common words it shares with
  queries ("this", "from", "the"). That cause was not isolated.
- With 48 tasks one task is worth 2.1 points. Small real effects will be missed. Tasks within a
  tool also share wording, so intervals may be somewhat too narrow.
- The sign-flip test uses 2000 rounds, so the smallest possible corrected p is about 0.003; every
  0.003 in the table means "at the floor", not an exact value.
- `first_sentence`, `drop_negative`, `boilerplate` and `identity` are deterministic, so their 20 seeds
  are repeated work. With `--cmd` and a nondeterministic model, `identity` would show the model's own
  noise, but the other rows are not corrected for it. The p-value reported for `identity` is always 1.
- Parameter schemas, tool names and tool-list order are not fuzzed. For the real model this is the main
  weakness: names leak the answer. The obvious next experiment is opaque names (`tool_1` ... `tool_12`),
  or harder tasks where two tools are plausible.
- The live run used one model, one seed count (3) and one tool order, and the exact model behind the
  headless CLI could not be independently confirmed.

## Run it
```bash
python examples/demo.py                          # both simulated selectors, offline
python examples/live_run.py --count --seeds 3    # how many real model calls a run needs (768)
python examples/live_run.py --seeds 3            # real Claude via headless Claude Code; cached
python examples/demo.py --seeds 1 --cmd "./pick"  # your own selector: JSON stdin, tool name stdout
pip install pytest && pytest
```
`--cmd` makes `48 x (2 + 8 x seeds)` calls and skips the one-tool-at-a-time table.
