# FDAS PR92 retained-capacity delayed-outcome preregistration

Date: 2026-08-04

## Question

PR91 established that scalar PF sometimes selects a grounded replacement-
capacity production operation whose exact queue is already authoritative, and
that the observer can later identify the exact produced unit. It deliberately
made no claim that product completion relieved the originating deficit.

PR92 asks whether those already-observed operations can be assigned durable,
restart-safe outcome labels that distinguish queue acceptance, exact product
effect, and delayed goal relief without granting the labeler any controller or
truth authority.

## Frozen outcome

The additive
`replacement_capacity_retained_queue_outcome=shadow-live` component opens one
idempotent label for each retained-queue operation. Its frozen target is
`durable-retained-replacement-capacity-relief/32-turn/1.0`.

An authoritative exact product moves a label from `pending_product` to
`pending_relief`; it does not count as goal relief. At product turn plus 32,
durable positive relief requires all seven conditions in the same current
snapshot/revision:

1. source city remains present and owned;
2. target city remains present and owned;
3. exact produced unit remains present;
4. exact produced unit remains owned;
5. exact produced unit type matches the queued type;
6. exact produced unit remains at the source city; and
7. the original dependent deficit atom is absent.

A missing conjunct is a delayed negative with the failed conjuncts recorded.
Lifecycle abandonment, expiry, or failure before product identity is an
immediate terminal no-progress label. Labels not yet due at the horizon remain
explicitly pending/right-censored. The store is atomic, digest-bound,
restart-safe, and quarantines corrupt state.

The component has no action-selection, induction-readout, policy, readout,
transition-value, or truth authority.

## Fixed diagnostic confirmation cohort

The 16 PR91 diagnostic seeds are rerun as fresh games from one new clean commit:

`111521, 111533, 111539, 111577, 111581, 111593, 111599, 111611, 111623,
111637, 111641, 111653, 111659, 111667, 111697, 111721`.

These seeds are not an unseen effectiveness sample: their retained-queue and
product yield was measured by PR91. They are appropriate for confirming the
new downstream attribution mechanism. All games remain in the denominator,
including zero-label, zero-product, and right-censored games. No game is
replaced, retried, resumed, or appended based on yield.

The corrected single-game engine smoke on seed `111539` is development
evidence, not part of this cohort. It observed two exact products, followed by
one durable positive and one negative at their respective 32-turn due points.
The negative recorded that the exact product was no longer present/owned/at
the source. This smoke fixes the cohort recurrence minima below; it is not used
to estimate a rate.

## Acceptance criteria

- all 16 games complete from one clean source commit without resume or
  infrastructure failure;
- every game passes the complete parent replacement-capacity audit chain;
- the outcome manifest capability and all ten semantic/non-authority fields
  match exactly;
- the persistent store has the expected identity, schema, label identities,
  state digests, aggregate digest, and no quarantine;
- retained-queue operation, label, and opened-event identities are one-to-one;
- opened, product-observed, and terminal-observed transitions are unique,
  ordered, typed, causal, and match the final persistent label;
- all eight outcome counters match event counts, current pending state, live
  status, and terminal summary exactly;
- every delayed relief is the exact seven-conjunct calculation at or after its
  frozen 32-turn due point;
- terminal lifecycle failures are immediate no-progress and have no product;
- pending labels are retained, and a pending-relief label is only censored if
  its due turn lies beyond the game horizon;
- every label/event retains zero action, induction, policy, readout,
  transition-value, and truth authority;
- labels occur in at least 2 of 16 games;
- exact products occur in at least 1 game;
- delayed relief is assessed in at least 1 game;
- at least 1 durable positive relief is observed; and
- the aggregate report is byte-identical on a second audit pass.

The minima are mechanism-recurrence gates, not rate or effectiveness claims.
Failure is retained as evidence.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr92-retained-capacity-outcome-v1 \
  --config profile/freeciv_harness_fdas_pr92_retained_capacity_outcome_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_replacement_capacity_retained_queue_outcome_cohort.py \
  artifacts/freeciv/fdas-pr92-retained-capacity-outcome-v1 \
  --expected-seeds 111521,111533,111539,111577,111581,111593,111599,111611,111623,111637,111641,111653,111659,111667,111697,111721 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --minimum-games-with-label 2 \
  --minimum-games-with-product 1 \
  --minimum-games-with-relief 1 \
  --minimum-positive-relief 1 \
  --output docs/freeciv/evidence/fdas-pr92-retained-capacity-outcome.json
```

## Claim boundary

A pass establishes recurrent, exact, engine-backed separation of retained
queue acceptance, exact produced-unit effect, and delayed durable
replacement-capacity relief on this diagnostic seed set. It does not establish
that PF caused the queue choice, estimate transition value, demonstrate score
or win-rate improvement, or estimate a general durable-relief rate.
