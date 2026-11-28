# cost-aware-router

> Learn from per-task eval results when a small model is good enough. Report cost per task next to
> held-out quality, with a confidence interval on the accuracy you gave up.

**Every number below is from simulated models.** No live model was run. The router reads an eval log
(JSONL, one row per task). The only logs used here came from a simulator whose difficulty curve and
self-agreement rates I picked. The `--records` path runs on any log in the same schema, but no real
log has been through it.

## Hypothesis
1. A router fitted on one eval log, given an accuracy budget ("at most 1 point worse than the large
   model"), keeps that budget on held-out tasks from the same distribution and cuts cost.
2. A per-task signal (does the small model agree with itself?) holds up better than a per-category
   rule when a category gets harder after the router was fit.

## Design
```
eval log (task, category, small_ok, large_ok, small_agree, costs)
     │ hash split on task_id
     ├─► train ─► CategoryGate.fit(cheap, expensive, max_drop) ─► allowed categories
     └─► test  ─► replay every policy offline ─► accuracy, cost/task, paired 95% CI vs large
```
- **Counterfactual replay.** Each record stores both models' outcomes, so any policy is scored on
  the same log with no new model calls. This only works if the log ran both models on every task.
- **Policies.** `always_small`, `always_large`, `oracle` (knows which one is right: the lower bound
  on cost), `cascade` (two small samples; if they disagree, call large), `category` (small on the
  fitted categories, large elsewhere), `category+cascade` (cascade on the fitted categories).
- **Fitting is a greedy knapsack.** Categories are sorted by accuracy lost per unit of cost saved and
  added while train accuracy stays within `max_drop` of `expensive` alone. Exact over 5 categories,
  and the decisions are easy to read ("cheap on: classify,extract").
- **Paired CI.** Both policies see the same tasks, so the CI is on the per-task difference (normal
  approximation). It is much tighter than comparing two independent accuracies would give.
- **Cost model.** 1 unit per 1K tokens on the small model; large costs 15x (an assumed ratio, not a
  quoted price). A cascade pays 2 small calls on every task, plus a large call when it escalates.
- **Simulator.** Five categories with hidden mean difficulty from 0.10 to 0.65. Both models are
  near-perfect below 0.15; after that, small accuracy drops 1.0 per unit of difficulty and large 0.3.
  The small model agrees with itself 90% of the time when right and 35% when wrong.
- **Tradeoff:** routing by category needs no extra calls and is easy to audit, but cannot tell an
  easy math task from a hard one. A cascade sees each task but always pays for two small calls.
  A learned per-prompt classifier, which sits between the two, is out of scope.

## Results
Simulated models. Train: 2,000 tasks (seed 1). Test: 2,000 tasks (seed 2). Python 3.9. Real output
of `python examples/demo.py`:

```console
SIMULATED models. Fit on 2000 tasks (seed 1), max drop 1 pt, large = 15x small cost

== held-out, same distribution, 2000 tasks (seed 2)
policy             accuracy     Δ vs large [95% CI]  cost/task vs large  escal.  notes
always_small          74.1%     -18.1 [-20.2,-15.9]      0.689       7%      0%
always_large          92.2%        +0.0 [+0.0,+0.0]     10.339     100%      0%
cascade               88.3%        -3.8 [-5.4,-2.3]      4.080      39%     23%
category              91.3%        -0.8 [-1.4,-0.3]      8.989      87%      0%  cheap on: extract
category+cascade      91.8%        -0.3 [-0.9,+0.3]      8.099      78%      6%  cheap on: classify,extract
oracle                97.0%        +4.9 [+4.0,+5.8]      3.401      33%      0%

== accuracy budget sweep; drift = classify and summarize +0.3 difficulty at test time
 budget  policy                     same Δ [95% CI]  cost        drift Δ [95% CI]  cost
  -0.5  category                  +0.0 [+0.0,+0.0]  100%        +0.0 [+0.0,+0.0]  100%
  -0.5  category+cascade          -0.1 [-0.6,+0.3]   90%        -0.2 [-0.6,+0.3]   91%
  -1.0  category                  -0.8 [-1.4,-0.3]   87%        -0.9 [-1.4,-0.3]   89%
  -1.0  category+cascade          -0.3 [-0.9,+0.3]   78%        -1.4 [-2.3,-0.6]   80%
  -2.0  category                  -0.8 [-1.4,-0.3]   87%        -0.9 [-1.4,-0.3]   89%
  -2.0  category+cascade          -0.3 [-1.3,+0.6]   66%        -2.7 [-4.0,-1.5]   68%
  -5.0  category                  -2.4 [-3.4,-1.5]   71%        -6.5 [-7.8,-5.1]   69%
  -5.0  category+cascade          -3.8 [-5.4,-2.3]   39%        -6.2 [-8.0,-4.5]   44%
 -10.0  category                  -4.9 [-6.2,-3.6]   54%     -12.5 [-14.3,-10.6]   48%
 -10.0  category+cascade          -3.8 [-5.4,-2.3]   39%        -6.2 [-8.0,-4.5]   44%
```

What this shows (all simulated):
- **Hypothesis 1 holds on the same distribution, but the savings are small at tight budgets.** With
  a 1-point budget, `category+cascade` loses 0.3 points (CI −0.9 to +0.3) and costs 78% of
  always-large. A 2-point budget gets it to 66%. The oracle costs 33%, so most of the possible
  savings are left on the table. A router that only sees the category can't find the easy tasks
  hidden inside hard categories.
- **A cascade alone is cheap but misses the budget.** It costs 39% but loses 3.8 points, because the
  small model agrees with itself on 35% of its wrong answers, and those are never escalated.
  Self-agreement is a leaky signal, and the size of the leak decides the result.
- **Hypothesis 2 is mixed.** Under drift the budget check made on train no longer holds. At 2 points,
  `category+cascade` loses 2.7 (CI −4.0 to −1.5) where it lost 0.3 before. At a 10-point budget,
  plain `category` loses 12.5 (over budget), while `category+cascade` loses 6.2 at a similar cost:
  the per-task agreement check catches part of the drift. At budgets of 1 to 2 points, plain
  `category` is the one that holds, but only because it routes just `extract`, which did not drift.
- **Takeaway:** an accuracy budget checked on an old eval log is a statement about that log.
  Re-fit and re-check it on fresh traffic; the paired CI shows when a change is noise.

## Failure modes
- **Simulated everything.** The difficulty curve, the 35% confident-wrong rate and the 15x price
  ratio are my choices. The ranking of policies depends on them, and real models will differ.
- **Logs must hold both models' outcomes on every task.** Production traffic usually ran one model,
  so replaying it is biased toward whatever the old router chose. That needs an exploration split
  or a separate offline eval.
- **Correctness is a boolean.** Partial credit, grader noise and an LLM judge's own errors are not
  modeled. Neither are latency, rate limits or the cost of running the grader.
- **The fit is greedy over categories and checked only on train.** With small categories it can
  overfit, and nothing re-checks the budget on held-out data or adds a safety margin for it.
- **The normal-approximation CI** is rough when the difference is near 0 or there are few tasks.
- **Two samples cost two calls.** A real cascade could use log-probs or one sample plus a verifier.
  The cost here is accurate only for the two-sample version.

## Run it
```bash
python examples/demo.py                       # simulated, offline
python examples/demo.py --records evals.jsonl # your log, split 50/50 by task_id hash
pip install pytest && pytest
```
One JSON object per line: `{"task_id", "category", "small_correct", "large_correct",
"small_agree", "small_cost", "large_cost"}`. `small_cost` is the price of one small call.
