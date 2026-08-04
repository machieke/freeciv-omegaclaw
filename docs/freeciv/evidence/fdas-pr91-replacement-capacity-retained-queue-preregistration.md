# FDAS PR91 retained replacement-capacity queue preregistration

Date: 2026-08-04

## Question

PR89 grounded exact delayed defender-production operations, while the first
PR90 selected-action smoke found zero exact matches across 22 legacy-selected
city-production actions. The candidates and the legacy controller frequently
chose different cities or products. That is a policy mismatch, not a missing
action identity.

PR91 asks a narrower question: when scalar PF already selects one grounded
replacement-capacity operation whose queue is already authoritative, can the
system observe that retained queue and its later terminal outcome without
submitting or crediting a queue action?

## Frozen mechanism

Behind the additive
`replacement_capacity_retained_queue_lifecycle=shadow-live` gate, the observer
requires exactly one pressure-selected grounded capacity operation whose
`initial_step_index` is 1 and whose byte-exact production action matches the
current authoritative city queue. Ambiguity fails closed.

The observer then:

1. registers a shadow operation with zero immediate expected relief;
2. records the existing queue as `queue-was-already-selected`;
3. submits no queue action and emits no `operation_step_committed` event;
4. completes only after a later authoritative snapshot identifies the exact
   produced unit; or
5. emits one terminal abandonment as soon as the authoritative queue diverges.

This gate is separate from the PR90 observer for exact legacy-selected actions.
It has no truth, candidate, readout, policy, or action authority.

## Fixed cohort

The first 16 seeds in
`profile/freeciv_harness_fdas_pr91_replacement_capacity_retained_queue_160_turn.yaml`
were unused when registered:

`111521, 111533, 111539, 111577, 111581, 111593, 111599, 111611, 111623,
111637, 111641, 111653, 111659, 111667, 111697, 111721`.

All 16 games remain in the denominator, including games with no selected
retained queue or no product observation. No seed is replaced, retried,
resumed, or appended based on yield. The remaining 14 registered seeds are
reserve-only.

## Acceptance criteria

- all 16 fixed games complete from one clean source commit without resume or
  infrastructure failure;
- every game passes the full parent replacement lifecycle, readout,
  opportunity, capacity, delayed-production, and PR90 selected-action audits;
- the manifest capability and its seven semantic/non-authority fields match
  exactly;
- selected, no-match, and ambiguous outcomes partition every evaluation;
- proposal, queue-observation, product, and failure event counts match both
  live status and the terminal summary;
- operation identities are unique, proposals and retained-queue observations
  are one-to-one, and every terminal identity was registered;
- every proposal proves pressure selection, exact current-queue identity, no
  submitted action, and zero immediate capacity-goal relief;
- no retained-queue lifecycle emits an action-commit event;
- a queue divergence is one terminal abandonment, not repeated blocked events;
- selected retained queues occur in at least 2 of 16 games;
- an authoritative product completion occurs in at least 1 of 16 games; and
- the aggregate audit is byte-identical on a second pass.

The recurrence and product thresholds are frozen before the fresh run. Failure
is retained as evidence; reserve seeds will not be used to rescue either gate.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr91-retained-capacity-queue-v1 \
  --config profile/freeciv_harness_fdas_pr91_replacement_capacity_retained_queue_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 16 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_replacement_capacity_retained_queue_cohort.py \
  artifacts/freeciv/fdas-pr91-retained-capacity-queue-v1 \
  --expected-seeds 111521,111533,111539,111577,111581,111593,111599,111611,111623,111637,111641,111653,111659,111667,111697,111721 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --minimum-games-with-selected-match 2 \
  --minimum-games-with-product-observation 1 \
  --output docs/freeciv/evidence/fdas-pr91-replacement-capacity-retained-queue.json
```

## Claim boundary

A pass establishes recurrence of PF-selected grounded capacity queues that were
already authoritative, and at least one later exact product observation. It
does not establish that PF caused queue selection, that the product relieved
the deficit, or that policy quality, score, or win rate improved.
