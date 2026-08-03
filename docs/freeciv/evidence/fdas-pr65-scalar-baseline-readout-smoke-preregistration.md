# FDAS PR65 protected scalar-baseline readout smoke preregistration

Date: 2026-08-03

## Question and semantic correction

PR64 established recurrent candidate-specific transition predictions and 20
protected additions, but its legacy-control readout never reached a candidate
comparison. In 128 of 135 evaluations, the selected live action was a move
with no unique FDAS reinforcement route. Most such live moves belong to other
planning purposes, so treating them as reinforcement controls would weaken the
same-target and grounded-noninferiority contract.

PR65 asks the narrower question the protected union can answer: does any
protected reinforcement candidate have a strictly separated calibrated
interval and exact grounded non-inferiority relative to the union's frozen
scalar top-1 FDAS candidate? The live action remains outside this diagnostic
and cannot change.

The PR58 legacy-control readout remains byte-for-byte unchanged and is absent
from the PR65 manifest. PR65 has a distinct identity,
`fdas-scalar-baseline-candidate-readout/1.0`, and declares control semantics
`protected-fdas-scalar-top-1` on every event.

## Frozen readout contract

The exact PR60 model, PR63 confirmation, scalar top-k `1`, calibrated-per-
action `1`, and maximum interval width `0.55` remain unchanged. The readout:

1. reconstructs the protected union's baseline operation and requires it to be
   baseline rank one;
2. requires the control to be an eligible, exact-grounded reinforcement move;
3. considers only members of the protected union;
4. requires an alternative to have the same operation type and city target,
   a distinct action and disjoint resource claims;
5. requires the alternative interval lower bound to be strictly above the
   control upper bound; and
6. requires no regression in unit type, route ETA, total or first-step
   movement cost, hit points, moves left, veteran level, or home-city relation.

Missing control support, a fortify scalar baseline, no protected alternative,
pair-scope mismatch, interval overlap, or a grounded mechanics regression
causes an explicit abstention. The event requires false action-selection,
policy, readout, and truth authority. Scalar score remains authoritative, and
flow and capacity solving remain disabled in the parent union.

## Fresh execution and acceptance

The fixed fresh seed is `109009`. The profile contains a schema-valid 30-seed
pool and executes only its first seed.

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr65-scalar-baseline-readout-smoke-v1 \
  --config profile/freeciv_harness_fdas_pr65_scalar_baseline_readout_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_scalar_baseline_candidate_readout.py \
  artifacts/freeciv/fdas-pr65-scalar-baseline-readout-smoke-v1 \
  --expected-seed 109009 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr65-scalar-baseline-readout-smoke.json
```

The smoke passes only if:

- seed `109009` reaches its horizon or a genuine absorbing terminal with no
  infrastructure failure or rejected action;
- the exact clean source, profile, manifest, model, artifact, and confirmation
  are hash-bound and the event ledger is valid without warnings;
- choice, union, scalar-baseline readout, and all status counters agree;
- the legacy-control readout is absent;
- every union and readout event is revision-current, hash-valid, and denies
  undeclared authority;
- at least one candidate-specific transition estimate is observed; and
- at least one protected alternative reaches a fully grounded comparison with
  the scalar control.

A separated diagnostic preference is not required. Honest interval overlap,
grounded inferiority, or other explicit abstention is a valid smoke result.

## Stop and claim boundary

- Preserve a failed run or audit as failed evidence.
- Do not retry, replace, add, or remove the seed after collection starts.
- Do not change the model, union, readout, thresholds, auditor, or endpoint
  contract after collection starts.
- Do not use a shadow preference as live action authority.

A pass establishes scalar-control alignment and shadow comparison mechanics
only. Nonselected outcomes remain censored; PR65 cannot establish cross-
candidate ranking quality, counterfactual value, gameplay, score, or win rate.
