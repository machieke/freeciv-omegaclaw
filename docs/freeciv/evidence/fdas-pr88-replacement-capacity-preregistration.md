# FDAS PR88 replacement-capacity demand preregistration

Date: 2026-08-04

## Question

PR87 found `no-safe-replacement-relation` in 819 of 1,437 evaluated
revisions. Exact replay of those revisions found 2,214 genuine alternative
actors whose removal would make their own source city unsafe, versus only 37
route-absent pairings after protected-self cases were excluded. PR88 asks
whether this missing spare-defender capacity can be represented as a typed
source-city demand and grounded to current legal defender-production actions.

PR88 does not weaken `defense.removal-deficit`, treat planned production as
current coverage, add candidates to the protected readout union, or change
ranking, transition value, scheduling, or action selection.

## Frozen mechanism

Behind the additive `replacement_capacity_demand=shadow-live` gate, a source
city receives `city-replacement-capacity-deficit(source,target)` exactly when:

1. one of its current persistent defenders is critical to the source
   garrison;
2. that defender has a current native reinforcement route to a different city
   with a factual garrison deficit; and
3. no different current persistent defender can safely and currently route to
   the protected source city.

When condition 3 becomes true, the same source-target key is represented by
`city-replacement-capacity-ready` instead. A deficit creates a survival goal
and binds only to byte-identical current legal `city_production` actions at the
source city whose target is a ruleset-grounded persistent defender. Repeating
the current queue is excluded. These candidates are shadow-only,
`authority_eligible=false`, and cannot enter policy or execution.

The predicates depend on city/unit membership, current native routes, the
current legal-action digest, ruleset identity, and the exact removal/route/ETA
grounding witnesses. Pressure remains control state and does not mutate the
factual predicates.

## Fixed cohort

The first 16 seeds in
`profile/freeciv_harness_fdas_pr88_replacement_capacity_160_turn.yaml` were
unused when registered:

`110749, 110753, 110771, 110777, 110807, 110813, 110819, 110821, 110849,
110863, 110881, 110909, 110917, 110921, 110923, 110939`.

All 16 games remain in the denominator. No seed is replaced, retried, resumed,
or appended based on capacity-goal or candidate frequency. The remaining 14
registered seeds are reserve-only.

## Acceptance criteria

- all 16 games complete from one clean source commit without resume or
  infrastructure failure;
- every game passes the existing lifecycle, readout, and opportunity-funnel
  audits;
- the manifest gate and its five non-authority fields match exactly;
- every FDAS shadow evaluation is counted and every game contributes at least
  one evaluation;
- capacity goal and production-candidate counters match the event ledger;
- every recorded capacity production candidate is current-revision,
  legal-bound, hash-identified, and explicitly non-authoritative; and
- the full aggregate audit is byte-identical on a second pass.

No nonzero capacity-goal or candidate frequency is required for mechanical
acceptance. Frequencies are descriptive, preventing the diagnostic hypothesis
from becoming an outcome-conditioned gate.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr88-replacement-capacity-v1 \
  --config profile/freeciv_harness_fdas_pr88_replacement_capacity_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 16 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_replacement_capacity_cohort.py \
  artifacts/freeciv/fdas-pr88-replacement-capacity-v1 \
  --expected-seeds 110749,110753,110771,110777,110807,110813,110819,110821,110849,110863,110881,110909,110917,110921,110923,110939 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr88-replacement-capacity.json
```

## Claim boundary

A pass establishes exact live representation and legal shadow recall of the
source-city capacity bottleneck. It does not establish production completion,
a safe replacement relation, transition value, preference, action, score, or
win-rate improvement. Any treatment requires a separate frozen authority and
outcome design.
