# FDAS PR75 calibrated-equivalence Pareto confirmation preregistration

Date: 2026-08-03

## Frozen correction

PR74 observed 30 grounded-noninferior alternatives but zero independently
separated marginal intervals. Twenty-eight of those alternatives had exactly
the same estimate, interval, effective lineage count, and calibration backoff
as their controls. Ten were also strictly better on at least one grounded
mechanical dimension.

PR75 adds a separately manifest-gated readout `1.2`. The existing interval-
separated route is unchanged and retains precedence. An overlapping candidate
may become a shadow preference only when:

- its estimate, lower/upper interval, effective lineages, and calibration
  reason exactly equal the control;
- it passes every existing grounded route, current-unit, and ruleset defensive
  noninferiority check; and
- it is strictly better on at least one of those ordered grounded dimensions.

There is no epsilon, interval shrinkage, estimate substitution, or action
authority. Missing provenance, an incomparable capability, any inferior
dimension, or no strict improvement abstains.

## Known-opportunity confirmation

Seed `109433` is deliberately reused because PR74 observed nine recurring
same-type exact-equivalence route-dominance opportunities there. This is a live
integration check, not independent opportunity or value evidence. The gate
requires the complete inherited safety audit, exclusive readout `1.2`, at least
one grounded alternative and strict improvement, and at least one equivalence-
Pareto shadow preference. Interval-separated preference is not required.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr75-calibrated-equivalence-pareto-confirmation-v1 \
  --config profile/freeciv_harness_fdas_pr75_calibrated_equivalence_pareto_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 39 --limit-seeds 1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_calibrated_equivalence_pareto_confirmation.py \
  artifacts/freeciv/fdas-pr75-calibrated-equivalence-pareto-confirmation-v1 \
  --expected-seed 109433 --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr75-calibrated-equivalence-pareto-confirmation.json
```

## Claim boundary

A pass confirms the new non-authorizing readout on a known opportunity only.
It does not establish counterfactual ranking quality, treatment effect,
gameplay impact, score improvement, or win rate.
