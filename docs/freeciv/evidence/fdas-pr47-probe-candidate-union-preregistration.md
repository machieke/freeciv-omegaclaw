# PR47 corrected-probe candidate-union confirmation preregistration

## Question

On fresh engine-backed games, do healthy corrected probes recurrently recall
one reachable defense candidate beyond the frozen calibrated candidate union,
while leaving scalar ranking and action selection unchanged?

## Frozen cohort

| Field | Frozen value |
|---|---|
| Backend | `engine-live` |
| Condition | `main/e_full_loop` only |
| Maximum horizon | 160 turns |
| Accepted endpoint | turn 160, engine game over, or player elimination |
| Ruleset | `civ2civ3` |
| Opponent | built-in experimental AI |
| Games | 8 |
| Seeds | `105337`, `105341`, `105359`, `105361`, `105367`, `105373`, `105379`, `105389` |
| Calibrated baseline | frozen PR40/PR42 model and PR45 protected union |
| Probe estimator | two-stream importance correction, 128 paths per direction |
| Maximum probe regions | `1` |
| Probe additions | at most `1` per action family and `1` total per union |
| Advection/capacity solver | disabled |
| Policy/readout authority | disabled |

An endpoint is accepted only when the run completes without infrastructure
failure and either reaches turn 160 or the engine explicitly reports game over
or player elimination. A short, interrupted, timed-out, or failed run remains
mechanically invalid.

## Frozen evidence dependencies

- PR40 discovery artifact hash:
  `b990cb2ce5dd973c4ded876b114986f3f54d52a358ed57d4f8e1078958d787d9`;
- calibration model hash:
  `9d2af28d765e75cfe3a0aade43be9d5f0a251904f605dd79394db93363a2562a`;
- PR42 confirmation report hash:
  `f1bd991a6d78a2554d1ed73f4e67c56c87f1b299c4e4f71db9ef26cc73ec9cc8`;
- PR45 protected-union report hash:
  `7c7a131ec2e1ec9bd01c03e96e667649eec6849a9afdd684268a8e32f8a2decf`;
- FDAS config:
  `profile/dependent_atomspace_defense_choice_surface_shadow.yaml`; and
- FDAS manifest:
  `profile/fdas_manifest_defense_probe_union_shadow.json`.

The PR46 engineering smoke and every earlier discovery, calibration,
confirmation, and protected-union seed are excluded.

## Mechanical acceptance gates

All eight games must:

- use the exact preregistered clean source commit and identical source
  identity;
- complete at an accepted endpoint without infrastructure failure;
- have zero rejected actions;
- produce event ledgers with zero validation errors and warnings;
- use the frozen FDAS config and probe manifest;
- emit one probe-union event per candidate choice set;
- bind every probe event to the exact snapshot and FDAS revision;
- bind every probe event to exactly one calibrated-union parent and reproduce
  its baseline membership, scalar winner, and result hash;
- reproduce probe-union and signal-ledger semantic hashes;
- use the exact frozen graph/probe configuration;
- keep every factor graph complete and every probe batch healthy;
- report zero probe fallbacks and incomplete graphs;
- select at most one positive-overlap probe region and add at most one member
  beyond the calibrated union;
- keep the scalar winner protected; and
- report zero action-selection changes, truth mutations, policy/readout
  authority, advection, and capacity solving.

## Frozen progression gates

- at least `300` probe-union events;
- at least `500` candidate reachability readouts;
- at least `8` mixed-action union opportunities;
- at least `8` probe additions beyond the calibrated union;
- at least `4` of `8` games with one or more additions; and
- a Wilson 95% lower bound of at least `0.10` for the proportion of games with
  an addition.

Passing establishes recurrent, bounded probe-informed candidate recall beyond
the calibrated union. It does not establish ranking quality, candidate quality,
counterfactual outcomes, gameplay impact, score improvement, or win rate.

## Stop rules

- Do not replace, extend, or pool seeds after execution starts.
- Do not change the estimator, one-region cap, thresholds, or endpoint
  semantics after inspecting PR47.
- Do not refit calibration on PR47.
- Preserve and report a mechanically rejected or progression-failing cohort
  as failed.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_choice_surface_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_probe_union_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-probe-candidate-union-confirmation-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 46 --limit-seeds 8 --condition e_full_loop \
  --main-only --no-resume
```

Frozen audit invocation:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_probe_candidate_union.py \
  artifacts/freeciv/fdas-probe-candidate-union-confirmation-v1 \
  --output docs/freeciv/evidence/fdas-pr47-probe-candidate-union.json \
  --cohort-id fdas_probe_candidate_union_confirmation_v1 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --expected-seed 105337 --expected-seed 105341 \
  --expected-seed 105359 --expected-seed 105361 \
  --expected-seed 105367 --expected-seed 105373 \
  --expected-seed 105379 --expected-seed 105389 \
  --minimum-union-events 300 \
  --minimum-probe-readouts 500 \
  --minimum-mixed-action-unions 8 \
  --minimum-probe-additions 8 \
  --minimum-games-with-additions 4 \
  --minimum-game-addition-rate-wilson-lower 0.10
```
