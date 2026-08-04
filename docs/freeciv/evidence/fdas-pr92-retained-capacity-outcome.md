# FDAS PR92 retained-capacity delayed-outcome evidence

Date: 2026-08-04  
Engine source commit: `db96e2045a118d13747ca8da199f88cf1c5cf2f2`  
Audit correction commit: `9e64b26`  
Profile: `freeciv_harness_fdas_pr92_retained_capacity_outcome_160_turn.yaml`

## Result

PR92 passes every preregistered engine, mechanics, recurrence, attribution,
non-authority, and reproducibility gate. All 16 fixed games reached turn 160
from one clean source commit with zero infrastructure failures, zero resumes,
and zero harness failures.

| Outcome boundary | Count | Games |
|---|---:|---:|
| Retained-queue labels opened | 7 | 4/16 |
| Exact products observed | 3 | 3/16 |
| Delayed relief assessments | 3 | 3/16 |
| Durable positive relief | 2 | 2/16 |
| Delayed negative relief | 1 | 1/16 |
| Immediate terminal no-progress | 4 | 3/16 |
| Pending/right-censored at horizon | 0 | 0/16 |

The cohort retained all 12 zero-label games. The raw rates are descriptive for
this previously characterized diagnostic seed set and are not estimates of a
general treatment effect or transition value.

## Exact terminal attribution

| Seed | Source → target | Product | Proposal/product/due | Result |
|---:|---|---|---|---|
| 111533 | 112 → 110 | Riflemen | 27/—/— | immediate queue-divergence no-progress |
| 111539 | 110 → 116 | Alpine Troops | 24/34/66 | durable positive |
| 111581 | 114 → 118 | Musketeers | 34/40/72 | delayed negative: exact product absent/not owned/not at source/type unavailable |
| 111581 | 110 → 103 | Musketeers | 20/—/— | immediate queue-divergence no-progress |
| 111667 | 109 → 117 | Alpine Troops | 24/—/— | immediate queue-divergence no-progress |
| 111667 | 113 → 124 | Alpine Troops | 29/—/— | immediate queue-divergence no-progress |
| 111667 | 101 → 124 | Riflemen | 29/33/65 | durable positive |

Product completion and goal relief remain separate transitions. Both positive
labels require the exact product, ownership, type, source placement, both city
ownership conjuncts, and absence of the original dependent deficit atom at
the 32-turn due point. The negative label records the failed product conjuncts
rather than crediting relief from deficit absence alone.

## Audit-composition correction

The first aggregate audit was rejected with structural hash
`c73dc96bb40b9c0b2f5bfb30d912a98d8d8c3119ca20292c8c1192a19553398b`.
Only `label_transitions_are_unique_ordered_and_causally_grounded` failed, in
seeds `111533`, `111581`, and `111667`.

RCA showed that every failure used the correct engine chain:

`operation_abandoned → atomspace_revision_started → snapshot_delta_computed
→ projection_batch_applied → atomspace_revision_committed → outcome label`.

The audit had incorrectly required `operation_abandoned` to be the direct
parent. The runtime must materialize a fresh exact dependent revision before
attributing a real terminal event received during same-turn action refresh;
therefore the four revision events are required causal bridges, not unrelated
intervening work.

Commit `9e64b26` corrects only the auditor. It accepts one linear, acyclic chain
through exactly those four event types to the exact registered operation's
terminal lifecycle event. Tests reject an unrelated bridge type, wrong
operation identity, and a causal cycle. No game was rerun or resumed, no event
or store was edited, and no threshold was changed.

## Audit result

The corrected aggregate report passes all gates and reproduced byte-for-byte
on an independent second invocation:

- structural hash:
  `e061c529bb31153316ab7947810ae3e35f25c4fa76a04e49dd411e8cb008528f`;
- JSON SHA-256:
  `25c2d5e15303a55b3870f4ace5fe95939710185cb3773fffe8b7b1fd04da43de`;
- run root: `artifacts/freeciv/fdas-pr92-retained-capacity-outcome-v1`;
- report: `fdas-pr92-retained-capacity-outcome.json`.

Every label is one-to-one with a retained-queue operation and is typed,
identity-bound, digest-valid, restart-safe, and terminally absorbing. Event,
status, terminal-summary, and current-pending counters agree exactly. No label
or event has action-selection, induction-readout, policy, readout,
transition-value, or truth authority.

## Claim boundary

This confirms an engine-backed mechanism for exact separation of an already
authoritative retained queue, its exact produced-unit effect, and its delayed
durable replacement-capacity relief/no-progress outcome. It does not establish
that PF caused the queue choice, does not estimate causal transition value,
and makes no score or win-rate improvement claim.

The next bounded step is to map these terminal labels into the common decision
episode vocabulary (`no-effect-observed`, `effect-without-goal-relief`, and
`goal-relief-observed`) without enabling learning or conductance authority.
