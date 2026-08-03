# PR49 path-persistence candidate-union confirmation preregistration

## Question

On fresh engine-backed games, does bounded temporal corridor persistence
recurrently retain one current legal defense candidate beyond the frozen
corrected-probe union, while leaving scalar ranking and action selection
unchanged?

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
| Seeds | `105397`, `105401`, `105407`, `105437`, `105449`, `105467`, `105491`, `105499` |
| Baseline | frozen scalar, calibrated union, and PR47 corrected-probe union |
| Smoothing/momentum | `0.35` / `0.15` |
| Dwell/bonus/switch margin | `2` / `0.05` / `0.01` |
| Maximum reachability regret | `0.05` |
| Persistence additions | at most `1` total per union |
| Advection/capacity/source--sink flow | disabled |
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
- PR47 corrected-probe report hash:
  `fad3de1c888ff87fab1968dd6a88e2c93e214a5c1671ab5f91cf27af861d3ef5`;
- FDAS config:
  `profile/dependent_atomspace_defense_choice_surface_shadow.yaml`;
- FDAS manifest:
  `profile/fdas_manifest_defense_path_persistence_union_shadow.json`; and
- harness profile:
  `profile/freeciv_harness_fdas_pr49_160_turn.yaml`.

The PR48 engineering seed and every earlier discovery, calibration,
confirmation, protected-union, and corrected-probe seed are excluded.

## Mechanical acceptance gates

All eight games must:

- use the exact preregistered clean source commit and identical source
  identity;
- complete at an accepted endpoint without infrastructure failure;
- have zero rejected actions;
- produce event ledgers with zero validation errors and warnings;
- use the exact frozen harness, FDAS config, and persistence manifest;
- emit one persistence-union event per candidate choice set;
- bind every persistence event to the exact snapshot and FDAS revision;
- bind every persistence event to exactly one corrected-probe parent and
  reproduce its baseline membership, scalar winner, and result hash;
- reproduce persistence-union and signal-ledger semantic hashes;
- preserve controller state continuity between successive decisions;
- use the exact frozen persistence configuration;
- expire every route absent from the exact current candidate surface;
- add at most one current candidate beyond the probe union;
- attribute smoothing, dwell, hysteresis, and regret rejection distinctly;
- reanchor any proposed retained candidate above the `0.05` instantaneous
  reachability-regret bound;
- keep the scalar winner and scalar order protected; and
- report zero fallbacks, action-selection changes, truth mutations,
  policy/readout authority, advection, capacity solving, and source--sink flow.

## Frozen progression gates

- at least `300` persistence-union events;
- at least `500` persistence readouts;
- at least `8` temporal retentions;
- at least `8` temporal additions beyond corrected probes;
- at least `1` observed regret-gate reanchor;
- at least `1` observed expired route;
- at least `4` of `8` games with one or more temporal additions; and
- a Wilson 95% lower bound of at least `0.10` for the proportion of games with
  a temporal addition.

A temporal addition counts only when the added member is retained by smoothing,
dwell, or hysteresis; an initial or non-temporal membership difference does not
count.

Passing establishes recurrent, bounded temporal candidate recall beyond the
corrected-probe union. It does not establish candidate precision, candidate
value, ranking quality, counterfactual outcomes, gameplay impact, score
improvement, or win rate.

## Historical safety boundary

PR49 does not re-evaluate or reactivate the old CT4 ranking-authority
controller. CT4's preregistered 30-pair pilot had a paired score delta of
`-0.167` and increased no-effect actions by `+0.50`. In PR49 all temporal
signals remain protected-membership-only, so identical gameplay across shadow
and baseline is expected by construction.

## Stop rules

- Do not replace, extend, or pool seeds after execution starts.
- Do not change the controller, regret bound, thresholds, endpoint semantics,
  or upstream calibrated/probe layers after inspecting PR49.
- Do not refit calibration on PR49.
- Preserve and report a mechanically rejected or progression-failing cohort
  as failed.
- Do not interpret descriptive game scores from this shadow-only cohort as an
  intervention effect.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_choice_surface_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_path_persistence_union_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-path-persistence-union-confirmation-v1 \
  --config profile/freeciv_harness_fdas_pr49_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 54 --limit-seeds 8 --condition e_full_loop \
  --main-only --no-resume
```

Frozen audit invocation:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_path_persistence_union.py \
  artifacts/freeciv/fdas-path-persistence-union-confirmation-v1 \
  --output docs/freeciv/evidence/fdas-pr49-path-persistence-union.json \
  --cohort-id fdas_path_persistence_union_confirmation_v1 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --expected-seed 105397 --expected-seed 105401 \
  --expected-seed 105407 --expected-seed 105437 \
  --expected-seed 105449 --expected-seed 105467 \
  --expected-seed 105491 --expected-seed 105499 \
  --minimum-union-events 300 \
  --minimum-persistence-readouts 500 \
  --minimum-temporal-retentions 8 \
  --minimum-temporal-additions 8 \
  --minimum-regret-rejections 1 \
  --minimum-expired-routes 1 \
  --minimum-games-with-temporal-additions 4 \
  --minimum-game-addition-rate-wilson-lower 0.10
```
