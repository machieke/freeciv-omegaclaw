# FDAS PR89 grounded replacement-capacity production preregistration

Date: 2026-08-04

## Question

PR88 found 1,789 typed replacement-capacity deficits and 2,837 legal
defender-production candidates across its fixed 16-game cohort. Every candidate
was still rejected by the generic `uncompiled-action-effect` blocker. PR89 asks
whether those current legal actions can instead be represented by the existing
ruleset-grounded production model and its exact delayed operation contract.

This is a mechanics and recurrence test. It does not rank, select, submit, or
learn value for any production action.

## Frozen mechanism

Behind the additive
`replacement_capacity_production_operation=shadow-live` gate, each current
legal persistent-defender production route for a replacement-capacity deficit
is passed through `GroundedProductionTransitionModel` and
`ProductionEnablingOperationAssembler`.

A grounded candidate must contain:

1. the byte-identical current server-advertised queue action;
2. an exact ruleset target profile and buildability witness;
3. a ruleset/state-grounded completion interval within a fixed 64-turn
   observation horizon;
4. a six-premise `RequirementSet` with complete initial premise packets;
5. hard-current queue/action claims when a switch is needed and conditional
   future production/upkeep claims; and
6. two distinct steps: queue selection, then later authoritative product
   observation.

An already selected matching queue is retained as a step-1 operation rather
than omitted. Unsupported or incomplete model input remains a typed abstention.
All candidates retain
`delayed-production-completion-unobserved`, remain
`authority_eligible=false`, and contribute zero immediate goal relief. A unit
under construction is not a garrison or operation participant.

## Fixed cohort

The first 16 seeds in
`profile/freeciv_harness_fdas_pr89_replacement_capacity_production_160_turn.yaml`
were unused when registered:

`111143, 111149, 111187, 111191, 111211, 111217, 111227, 111229, 111253,
111263, 111269, 111271, 111301, 111317, 111323, 111337`.

All 16 games remain in the denominator. No seed is replaced, retried, resumed,
or appended based on grounded-operation yield. The remaining 14 registered
seeds are reserve-only.

## Acceptance criteria

- all 16 games complete from one clean source commit without resume or
  infrastructure failure;
- every game passes the existing replacement lifecycle, readout,
  opportunity-funnel, and replacement-capacity audits;
- the new manifest gate and its eight non-authority/semantic fields match
  exactly;
- grounded and abstained candidates partition every emitted
  replacement-capacity production candidate;
- every grounded candidate is rejected from immediate relief, has exactly two
  steps, a nonempty RequirementSet identity, at least one exact resource claim,
  and a completion interval inside the declared horizon;
- every ungrounded candidate has a typed fail-closed blocker;
- event-ledger counts exactly match status and terminal counters;
- at least one grounded operation occurs and grounded operations recur in at
  least 4 of 16 games; and
- the full aggregate audit is byte-identical on a second pass.

The recurrence threshold establishes that the mechanism is not a synthetic-only
path. It does not establish production completion or outcome quality.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr89-replacement-capacity-production-v1 \
  --config profile/freeciv_harness_fdas_pr89_replacement_capacity_production_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 16 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_replacement_capacity_production_cohort.py \
  artifacts/freeciv/fdas-pr89-replacement-capacity-production-v1 \
  --expected-seeds 111143,111149,111187,111191,111211,111217,111227,111229,111253,111263,111269,111271,111301,111317,111323,111337 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr89-replacement-capacity-production.json
```

## Claim boundary

A pass establishes live recurrence of exact delayed defender-production
candidate mechanics, RequirementSets, and resource claims for the PR88
capacity deficit. It does not establish that the legacy policy selects the
queue, that a defender completes, that replacement capacity becomes ready, or
that score or win rate improves. Those require a later lifecycle/outcome and
authority design.
