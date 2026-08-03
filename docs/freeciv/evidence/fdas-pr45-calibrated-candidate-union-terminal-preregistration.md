# PR45 calibrated candidate-union terminal-aware confirmation preregistration

## Question

On fresh engine-backed games, does the frozen calibrated protected union
repeatedly recall confidence-bounded defense candidates beyond unchanged
scalar top-1 when genuine absorbing terminal states are treated as completed
endpoints?

This is a new cohort, not a repair or extension of PR44. PR44 remains rejected
and none of its games contribute to PR45.

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
| Seeds | `105211`, `105227`, `105229`, `105251`, `105253`, `105269`, `105277`, `105319` |
| Scalar protected set | top `1` |
| Calibrated additions | at most `1` per action family |
| Maximum interval width | `0.55` |
| Maximum union size | `3` |
| Advection/capacity solver | disabled |
| Policy/readout authority | disabled |

An absorbing endpoint is accepted only when the run is completed without
infrastructure failure and the engine explicitly reports `terminal_game_over`
or `terminal_player_elimination`. An arbitrary short, interrupted, timed-out,
or failed run remains mechanically invalid.

## Frozen evidence dependencies

- PR40 discovery artifact hash:
  `b990cb2ce5dd973c4ded876b114986f3f54d52a358ed57d4f8e1078958d787d9`;
- calibration model hash:
  `9d2af28d765e75cfe3a0aade43be9d5f0a251904f605dd79394db93363a2562a`;
- PR42 confirmation report hash:
  `f1bd991a6d78a2554d1ed73f4e67c56c87f1b299c4e4f71db9ef26cc73ec9cc8`;
- FDAS config:
  `profile/dependent_atomspace_defense_choice_surface_shadow.yaml`; and
- FDAS manifest:
  `profile/fdas_manifest_defense_calibrated_union_shadow.json`.

## Mechanical acceptance gates

All eight games must:

- use the exact preregistered clean source commit and identical source
  identity;
- complete either turn 160 or a genuine declared absorbing endpoint, without
  infrastructure failure;
- have zero rejected actions;
- produce event ledgers with zero validation errors and warnings;
- use the frozen FDAS config and manifest;
- emit one calibrated-union event per candidate choice set;
- bind every event to its exact snapshot and revision;
- reproduce union hashes and status counters;
- protect scalar top-1 and keep union size at most three;
- add only confidence-eligible candidates, at most one per action family;
- record unsupported and wide-interval candidates as abstentions; and
- report zero action-selection changes, truth mutations, policy/readout
  authority, advection, and capacity solving.

## Frozen progression gates

The PR44 progression thresholds are retained exactly:

- at least `300` calibrated-union events;
- at least `50` eligible readouts;
- at least `8` mixed-action union opportunities;
- at least `8` calibrated additions beyond scalar top-1;
- at least `4` of `8` games with one or more additions; and
- a Wilson 95% lower bound of at least `0.10` for the proportion of games with
  an addition.

Passing establishes recurrent protected candidate recall and permits the next
shadow-only step, probe-informed reachability. It does not authorize calibrated
ranking, action selection, gameplay impact, score, or win-rate claims.

## Stop rules

- Do not replace, extend, or pool seeds after execution starts.
- Do not change thresholds or endpoint semantics after inspecting PR45.
- Do not refit calibration on PR45.
- Do not pool any earlier cohort.
- Preserve and report a failed mechanical or progression result as failed.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_choice_surface_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_calibrated_union_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-calibrated-candidate-union-confirmation-v2 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 38 --limit-seeds 8 --condition e_full_loop \
  --main-only --no-resume
```

Frozen audit invocation:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_calibrated_candidate_union.py \
  artifacts/freeciv/fdas-calibrated-candidate-union-confirmation-v2 \
  --output docs/freeciv/evidence/fdas-pr45-calibrated-candidate-union.json \
  --cohort-id fdas_calibrated_candidate_union_confirmation_v2 \
  --allow-absorbing-terminal \
  --expected-source-commit "$SOURCE_COMMIT" \
  --expected-seed 105211 --expected-seed 105227 \
  --expected-seed 105229 --expected-seed 105251 \
  --expected-seed 105253 --expected-seed 105269 \
  --expected-seed 105277 --expected-seed 105319 \
  --minimum-union-readouts 300 \
  --minimum-eligible-readouts 50 \
  --minimum-mixed-action-unions 8 \
  --minimum-calibrated-additions 8 \
  --minimum-games-with-additions 4 \
  --minimum-game-addition-rate-wilson-lower 0.10
```
