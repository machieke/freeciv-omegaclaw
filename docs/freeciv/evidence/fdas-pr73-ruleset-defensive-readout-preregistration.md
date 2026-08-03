# FDAS PR73 ruleset-defensive readout confirmation preregistration

Date: 2026-08-03

## Frozen correction

PR71 produced one same-target comparison in which the Alpine Troops
alternative arrived one turn sooner than the Riflemen scalar control, but the
readout's exact unit-name equality was not a defensive mechanic. PR73 versions
the readout to `1.1` and replaces that predicate only when explicitly enabled.
The replacement requires exact unit class and defensive-effect signature plus
componentwise noninferiority in compiled-ruleset defense, maximum hit points,
and firepower. Current hit points, veteran level, movement, route, target,
interval separation, safety filtering, and all authority prohibitions remain
unchanged. Missing or ambiguous ruleset data abstains.

## Known-opportunity confirmation

This first live integration check deliberately reuses seed `109229`, where
PR71 observed the only prior grounded same-target alternative. It tests whether
the newly versioned event and ruleset profiles traverse the real engine path.
It is not an independent yield or value cohort and cannot change the PR71
result.

The frozen gates require the complete safety-filter, target-filter, calibrated
union, and scalar-readout chain to pass; only readout `1.1` may appear; and at
least one different-unit-type comparison must record all five ruleset defensive
checks without a unit-name check. A preference is not required because the
calibrated intervals remain frozen.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr73-ruleset-defensive-readout-confirmation-v1 \
  --config profile/freeciv_harness_fdas_pr73_ruleset_defensive_scalar_readout_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 19 --limit-seeds 1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_ruleset_defensive_scalar_readout.py \
  artifacts/freeciv/fdas-pr73-ruleset-defensive-readout-confirmation-v1 \
  --expected-seed 109229 --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr73-ruleset-defensive-readout-confirmation.json
```

## Claim boundary

A pass confirms ruleset-grounded cross-type comparison mechanics on a known
engine opportunity. It establishes no independent recall rate, calibrated
ranking quality, counterfactual outcome, gameplay impact, score improvement,
or win rate and grants no action authority.
