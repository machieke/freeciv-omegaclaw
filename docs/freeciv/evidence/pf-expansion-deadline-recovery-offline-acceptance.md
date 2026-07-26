# PF-PLN expansion deadline recovery offline acceptance

Status: implementation and offline acceptance passed; fresh score claim not
attempted

## Correctness gap

Adapter `grounded-impact-planner/1.5` enforced
`expansion_minimum_settlement_runway_turns` when founder production began,
but an already-created founder could continue moving or found a city after
that same fixed-horizon runway was no longer achievable. The mismatch could
spend late action budget and retain population in a founder that could no
longer create the score-bearing city assumed by its production projection.

Post-outcome diagnostics from the immutable
`expansion_target_confirmatory_v1` cohort motivated this check but are not
used to revise that result. The confirmation remains an adapter-1.5 claim.

## Adapter 1.6 contract

`grounded-impact-planner/1.6` applies one runway contract across the founder
lifecycle:

- founder production still requires its projected settlement to preserve the
  configured post-settlement runway;
- immediate city founding remains valid when the remaining runway is exactly
  the configured minimum;
- city founding is rejected after that boundary;
- a founder requiring another movement action at the exact boundary no longer
  pursues expansion;
- if the active ruleset proves that founder has `Cities`, `AddToCity`, and a
  positive population cost, it routes strictly toward an owned city and uses
  an exact server-advertised `unit_join_city` action to recover population;
- without those exact capabilities or a strictly closer move, recovery fails
  closed; and
- the default zero runway preserves historical selection behavior.

Population recovery remains effect-checked: the founder must disappear and
the exact target city's population must increase by the compiled population
cost. Target-complete static-policy behavior is unchanged.

The boolean
`expansion_settlement_deadline_recovery_enabled` makes this lifecycle rule
explicit and ablatable. It defaults to `true` in adapter 1.6 and in the live
harness. Setting it to `false` restores the adapter-1.5 existing-founder
behavior without changing founder-production runway checks; it is intended
for controlled evaluation, not as an alternative recommended policy.

## Acceptance

Focused boundary tests cover exact-deadline settlement, late-settlement
rejection, deadline recovery movement and joining, capability failure, target
completion, and zero-runway compatibility.

The combined validation command completed with **200 passed**:

```bash
PYTHONPATH=src:benchmarks python3 -m pytest -q \
  Autotests/test_freeciv_impact.py \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_pf_runtime.py \
  Autotests/test_freeciv_harness.py
```

Deterministic authoritative-snapshot replay remains selection-invariant:
zero changed actions, zero changed categories, and unchanged input states.
The refreshed replay artifact hash is
`c1c5445e8b33bcbb9506b9870a2b48f20133710f68c8c7ade001bac35017da5c`.
The canonical `audit_pf_pln.py --workers 4` audit also passes every phase,
runtime-activation, generated-schema, artifact-fingerprint, and self-hash
check.

This is correctness and action-efficiency evidence, not a new gameplay score,
score-margin, or win-rate claim. Any empirical effect of deadline recovery
requires a fresh, predeclared, seed-disjoint paired cohort. The confirmed
+2.66 adapter-1.5 expansion-target result remains immutable and unpooled.

## Fresh engine diagnostic

`expansion_deadline_recovery_diagnostic_v1` predeclares 40 fresh, disjoint,
claim-ineligible turn-60 pairs from namespace
`pf-pln-expansion-deadline-recovery-diagnostic-v1`, range
`3800000..3899999`. Both arms target four cities, require a 15-turn
post-settlement runway, and enable pressure, conductance learning, and score
alignment. The only effective difference is
`expansion_settlement_deadline_recovery_enabled`: false under baseline and
true under treatment.

The diagnostic must complete all 40 pairs on one clean source identity,
validate all 80 event streams, replay every treatment pressure decision, and
report recovery activation, score, margin, and lead estimates regardless of
direction. It remains exploratory and cannot revise or be pooled with the
claim-eligible expansion confirmation.

The diagnostic completed all 40 pairs and every validation gate. Deadline
recovery activated in 10 treatment games, made 31 route attempts, completed
14 exact joins, and restored 28 population. It prevented four late
settlements. Paired score changed by -0.075 with interval [-0.400, +0.250]
and exact `p=0.765625`; lead rate changed by +2.5 percentage points with one
discordant pair and exact McNemar `p=1.0`. All 80 streams and 115,810 events
validated, and exact replay covered 2,985 treatment decisions with zero
integrity failures. This supports the correctness mechanism, not a score or
win-rate improvement. Full evidence is in
[`pf-expansion-deadline-recovery-diagnostic-v1.md`](pf-expansion-deadline-recovery-diagnostic-v1.md).
