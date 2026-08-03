# FDAS PR77 coordinated-replacement live-wiring preregistration

Date: 2026-08-03

## Frozen correction

PR76 identifies safe same-target candidate generation, especially coordinated
replacement of a protected source garrison, as the next bottleneck. The typed
candidate, two-step lifecycle adapter, persistent `OperationStore` projection,
bindings, `RequirementSet`s, and manifest capability already existed. Engine
inspection found that the live harness did not instantiate or reconcile that
adapter, so the declared `shadow-live` lifecycle produced neither a durable
store nor lifecycle evidence.

PR77 connects only this existing shadow mechanism. A live run now:

- creates a game- and attempt-bound replacement operation store;
- reconciles exact `fdas-defense:coordinated-replacement` candidates after the
  current FDAS shadow evaluation;
- projects persistent operation records, current legal bindings, resource
  claims, and requirement contexts into the same snapshot revision;
- rematerializes before emitting each revision-current lifecycle event; and
- records candidate, operation, reconciliation, block, step, completion, and
  expiry counters in status and terminal evidence.

Snapshot-specific operation IDs are deduplicated by the logical tuple of
replacement actor, reinforcement actor, source city, and deficit city. All
lifecycle events explicitly retain zero policy, readout, action-selection, and
truth authority. The baseline action selection is unchanged.

## Known-seed integration gate

Seed `109459` is deliberately reused because PR76 showed a rich defense choice
surface there. It is an integration smoke, not independent opportunity or
value evidence. Zero coordinated-replacement opportunity is mechanically
acceptable because the persistent empty store proves activation; component
fixtures separately require a real two-step lifecycle, source-garrison safety,
logical deduplication, and fail-closed completion.

The engine evidence passes only if:

- the event ledger is schema-valid without warnings;
- the source is clean and the 160-turn horizon completes;
- the manifest activates operation projection and the replacement capability
  as `shadow-live`;
- the persistent store is hash-valid, identity-bound, and unquarantined;
- every stored spec is a valid coordinated-replacement operation;
- no two active records represent the same logical lifecycle;
- every lifecycle event is snapshot-bound and non-authorizing;
- every lifecycle event references a persistent operation; and
- status and terminal counters exactly match durable events and records.

## Failed first attempt and frozen correction

Artifact `fdas-pr77-coordinated-replacement-live-wiring-v1` is retained as a
failed attempt. It reached turn 33, where the first replacement opportunity
failed closed with `replacement operation ruleset changed`. The harness had
constructed the adapter with `structural_hash(ir.to_dict())`, while the
candidate factory correctly used the canonical FDAS identity over compiler,
ruleset, semantics, and source hashes. The only correction is to use the same
canonical identity through both paths, guarded by a regression test. The `v2`
confirmation starts from a new clean commit and directory; it does not resume
or overwrite `v1`.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr77-coordinated-replacement-live-wiring-v2 \
  --config profile/freeciv_harness_fdas_pr77_replacement_live_wiring_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --seed-offset 43 --limit-seeds 1 --no-resume

GAME_DIR=artifacts/freeciv/fdas-pr77-coordinated-replacement-live-wiring-v2/games/main/e_full_loop/109459-00
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_replacement_live.py \
  --game-dir "$GAME_DIR" \
  --output docs/freeciv/evidence/fdas-pr77-coordinated-replacement-live-wiring.json
```

The audit is rerun to a temporary path and compared byte-for-byte to establish
deterministic report construction.

## Claim boundary

A pass establishes only that coordinated-replacement candidates can enter one
durable, deduplicated, revision-current, non-authorizing live lifecycle. It
does not establish opportunity frequency, candidate preference, causal action
value, score improvement, or win rate. A later fresh-seed opportunity cohort
is required before any randomized outcome pilot.
