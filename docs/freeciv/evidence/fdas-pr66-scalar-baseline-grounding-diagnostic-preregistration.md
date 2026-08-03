# FDAS PR66 scalar-baseline grounding diagnostic preregistration

Date: 2026-08-03

## Purpose

PR65 showed 73 completely grounded, candidate-specific move predictions, yet
the decision-safe control layer returned the same generic
`control-grounded-transition-input-unavailable` reason for all of them. That
reason combines stricter legality, goal/deficit support, native-route,
resource, blocker, and unit-field checks, preventing root-cause attribution.

PR66 changes observability only. The legacy PR58 readout preserves its frozen
generic reason. The separate scalar-baseline evaluator exposes the exact
fail-closed predicate returned by the existing validator or subsequent state
check. It does not remove, reorder, or relax a predicate, change calibration,
alter union membership, or grant authority.

## Frozen diagnostic contract

Exact reasons include the bounded reinforcement validator reason or a specific
missing deficit record, actor, city, native route, route revision/reachability,
ETA, or actor-field condition. Every such condition still abstains. The event
identity, protected scalar control, same-target/resource scope, interval gate,
grounded non-inferiority, model, and manifest remain unchanged.

The audit accepts only if the parent PR65 mechanical audit is accepted, at
least one candidate-specific prediction occurs, at least one exact scalar-
control grounding failure is observed, and the generic reason count is zero.
It deliberately does not require an alternative, comparison, or preference.

## Fresh execution

Seed `109021` is the second fixed seed in the PR65 profile and is executed with
an explicit offset. It is fresh relative to PR64 and PR65.

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr66-scalar-baseline-grounding-diagnostic-v1 \
  --config profile/freeciv_harness_fdas_pr65_scalar_baseline_readout_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 1 --limit-seeds 1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_scalar_baseline_grounding_diagnostic.py \
  artifacts/freeciv/fdas-pr66-scalar-baseline-grounding-diagnostic-v1 \
  --expected-seed 109021 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr66-scalar-baseline-grounding-diagnostic.json
```

## Stop and claim boundary

- Preserve a failed run or audit as failed evidence.
- Do not retry, replace, add, or remove the fixed seed.
- Do not alter predicates or reason classification after collection begins.
- Do not interpret reason counts as candidate opportunity or decision value.

A pass identifies which existing safety predicate blocks grounding. It makes
no candidate-yield, preference, ranking, counterfactual, gameplay, score, or
win-rate claim and permits no action authority.
