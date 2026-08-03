# FDAS PR70 PR68 pair-scope sensitivity specification

Date: 2026-08-03

## Status and purpose

This is an explicitly post-hoc diagnostic sensitivity, not a fresh experiment.
PR68 remains failed because its live readout emitted only aggregate scope
reasons, and PR69 remains failed because no addition coincided with a grounded
control. PR70 deterministically materializes the exact evidence already stored
for PR68's six aggregate rejections.

## Frozen reconstruction

For each PR68 scalar rejection ending in `pair-scope-mismatch`, the analyzer:

1. resolves the hash-bound protected union named by the readout;
2. resolves the union's sole causal safety-filter parent;
3. joins baseline and alternative by operation ID in both parents;
4. reads canonical actions and operation types from the union;
5. uses bounded target-support atom identity from the validated filter rows;
6. reconstructs ordinary unit resources with the committed
   `CandidateOperationFactory._resource` rule, `unit-action:<actor_id>`; and
7. records distinct-action, operation-type, bounded-target-support, identical-
   resource, and shared-resource predicates in a hash-bound row.

The analyzer first reruns the frozen PR68 parent audit and requires its exact
primary report hash. It fails closed on a missing parent, missing candidate,
malformed action, or non-unit resource.

## Sensitivity gates

The report expects the six already-observed aggregate rows and tests whether
all six are distinct actions with matching operation type, matching bounded
target support, and one identical inferred actor resource. These checks were
motivated by post-hoc inspection and therefore cannot serve as independent
confirmation.

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_pr68_pair_scope_sensitivity.py \
  artifacts/freeciv/fdas-pr68-safe-filtered-scalar-readout-opportunity-v1 \
  --expected-seed 109037 \
  --expected-seed 109049 \
  --expected-seed 109063 \
  --expected-seed 109073 \
  --expected-seed 109097 \
  --expected-seed 109103 \
  --expected-seed 109111 \
  --expected-seed 109121 \
  --expected-source-commit 66d153f9f1529a78c147d2ce269cb401ccdd11ae \
  --output docs/freeciv/evidence/fdas-pr70-pr68-pair-scope-sensitivity.json
```

## Claim boundary

A pass identifies the stored scope conjuncts and may motivate a new protected
substitution contract. It cannot make PR68 or PR69 pass, cannot establish an
alternative's value, and makes no fresh-confirmation, ranking, counterfactual,
gameplay, score, or win-rate claim. It changes no runtime or authority.
