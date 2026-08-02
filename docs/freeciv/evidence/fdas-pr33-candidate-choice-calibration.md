# FDAS PR33 outcome-safe candidate choice calibration

Status: durable selected-only evidence path implemented and engine-smoke
validated; the first smoke has no negative selected outcomes or multi-candidate
selected decisions, so it is not yet a calibration, ranking, gameplay, score,
or win-rate claim.

## Mechanism

PR33 closes the evidence-loss boundary found by PR32. Every evaluated
category-local choice now persists:

- the exact snapshot and dependent revision;
- every offered operation and legal action key;
- its outcome-free causal feature query;
- baseline, population-baseline, and contextual shadow priorities and ranks;
- the actually selected in-scope operation, when one exists;
- explicit `nonselected-censored` roles for all alternatives;
- execution acceptance or rejection; and
- a delayed outcome only through the selected operation's linked decision
  episode and exact outcome-label identity.

The atomic store is bound to the approved-rule report, consolidation report,
outcome target, attempt, and game. It validates immutable and store digests on
load and quarantines malformed or tampered artifacts. Restart recovery may
resolve an already-observed linked label, but it cannot infer a missing
selection or outcome.

The calibration export emits an `InductionEpisode` only for a selected row
whose delayed outcome is observed. A pending selected row remains pending; an
execution rejection, accepted action without a linked episode, out-of-scope
decision, and every nonselected row remain censored. In particular, rejecting
an alternative is never interpreted as evidence that the alternative would
have failed.

Truth, readout, policy, and action-selection authority remain false throughout.

## Engine-backed diagnostic smoke

The exact implementation was exercised for 160 turns on pinned seed `4543804`
with the PR32 candidate-impact profile and `qwen3-coder-next:latest` at
temperature zero. The run reached the horizon and completed with:

| Measure | Result |
|---|---:|
| Engine actions | 367 |
| Rejected actions | 0 |
| Valid events | 31,103 |
| Event validation errors / warnings | 0 / 0 |
| Candidate-impact evaluations | 6 |
| Complete candidate-impact coverages | 6 |
| Durable choice sets / choices | 6 / 6 |
| In-scope selected choices | 5 |
| No-in-scope-selection sets | 1 |
| Explicitly censored choices | 1 |
| Observed selected outcomes | 5 |
| Positive / negative selected outcomes | 5 / 0 |
| Pending selected outcomes | 0 |

All six machine-audit gates passed. The choice store has digest
`ff24e7cebf6890a58c31f2220a5c36ceda8a8760c83a2c399ff7af17e3241c8b`;
the audit report hash is
`b19c028fffb345c9c7316f26c76c4f6979ab2bc5057c5b5d3209de9f22057202`.
The generated report is `fdas-pr33-candidate-choice-smoke.json`.

This smoke was intentionally run from commit `af0b101` with the live-wiring
worktree dirty. It proves the implementation path, not a clean frozen cohort.

## Scientific boundary and next gate

This seed offered one in-category candidate per evaluated decision. It proves
selected/censored semantics and delayed outcome linkage, but cannot estimate
actor-relative treatment value. All five selected outcomes were positive, so
the sample also lacks outcome contrast.

The next valid experiment must be preregistered and collected from clean
source. It needs independent games with:

1. multiple same-category candidates in the same decision;
2. variation in which actor is actually selected;
3. both positive and negative selected delayed outcomes;
4. lifecycle/action-category strata fixed before fitting;
5. uncertainty intervals and held-out calibration gates; and
6. candidate-rank evaluation on a disjoint confirmation cohort.

No flow-controller retuning or bounded authority expansion is justified by
this smoke.

## Reproduction

```bash
PYTHONPATH=src python3 scripts/freeciv/audit_fdas_candidate_choices.py \
  artifacts/freeciv/fdas-candidate-choice-smoke-live-160-v1/games/main/e_full_loop/4543804-00/fdas-candidate-choice-sets.json \
  --output docs/freeciv/evidence/fdas-pr33-candidate-choice-smoke.json
```
