# PR44 calibrated candidate-union confirmation preregistration

## Question

On fresh engine-backed FreeCiv games, does the frozen calibrated protected
union repeatedly recall confidence-bounded defense candidates beyond the
unchanged scalar top-1 set, while leaving action selection and every authority
boundary unchanged?

This cohort tests candidate recall only. It does not test censored outcomes,
candidate ranking, action quality, gameplay impact, score, or win rate.

## Frozen cohort

| Field | Frozen value |
|---|---|
| Backend | `engine-live` |
| Condition | `main/e_full_loop` only |
| Horizon | 160 turns |
| Ruleset | `civ2civ3` |
| Opponent | built-in experimental AI |
| Games | 8 |
| Seeds | `105097`, `105107`, `105121`, `105137`, `105143`, `105167`, `105173`, `105199` |
| Scalar protected set | top `1` |
| Calibrated additions | at most `1` per action family |
| Maximum interval width | `0.55` |
| Maximum union size | `3` |
| Advection | disabled |
| Capacity solver | disabled |
| Policy/readout authority | disabled |

The discovery games, PR42 confirmation games, and PR43 smoke game are excluded
from this cohort.

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

- use exactly the preregistered clean source commit and identical source
  identity;
- complete the fixed horizon without infrastructure failure;
- have zero rejected actions;
- produce event ledgers with zero validation errors and zero warnings;
- use the frozen FDAS config and manifest;
- emit one calibrated-union event for every recorded candidate choice set;
- bind every union to the exact snapshot and revision;
- reproduce every union result hash;
- reproduce status counters from the event stream;
- keep scalar top-1 protected;
- keep each union at no more than three members;
- add only eligible predictions with interval width at most `0.55`;
- record every unsupported or wide-interval prediction as an abstention;
- add no more than one candidate per action family; and
- report zero action-selection changes, truth mutations, policy/readout
  authority, advection, and capacity solving.

Failure of any mechanical gate rejects the cohort.

## Frozen progression gates

Across the accepted cohort, all of these must pass:

- at least `300` calibrated-union events;
- at least `50` eligible candidate readouts;
- at least `8` mixed-action union opportunities;
- at least `8` calibrated additions beyond scalar top-1;
- at least `4` of the `8` games contain one or more additions; and
- the Wilson 95% lower bound for the proportion of games with an addition is
  at least `0.10`.

These thresholds were set before seeing any of the eight cohort games. They
are conservative relative to the retrospective, claim-ineligible PR42 design
yield of 22 additions in 6 of 8 games.

Passing establishes that calibrated protected recall is recurrent on fresh
games and permits progression to probe-informed reachability in shadow. It
does not authorize calibrated ranking or action selection.

## Stop rules

- Do not replace, extend, or pool seeds after execution starts.
- Do not change thresholds after inspecting any cohort outcome.
- Do not refit calibration on these games.
- Do not pool discovery, PR42 confirmation, or PR43 smoke artifacts.
- If a mechanical gate fails, repair the implementation and preregister a new
  cohort with new seeds.
- If only progression fails, preserve the result and do not relabel it as a
  passing recall claim.

## Frozen execution

Run from a clean checkout of the commit containing this preregistration:

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_choice_surface_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_calibrated_union_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-calibrated-candidate-union-confirmation-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 30 --limit-seeds 8 --condition e_full_loop \
  --main-only --no-resume
```

Frozen audit invocation:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_calibrated_candidate_union.py \
  artifacts/freeciv/fdas-calibrated-candidate-union-confirmation-v1 \
  --output docs/freeciv/evidence/fdas-pr44-calibrated-candidate-union.json \
  --expected-source-commit "$SOURCE_COMMIT" \
  --expected-seed 105097 --expected-seed 105107 \
  --expected-seed 105121 --expected-seed 105137 \
  --expected-seed 105143 --expected-seed 105167 \
  --expected-seed 105173 --expected-seed 105199 \
  --minimum-union-readouts 300 \
  --minimum-eligible-readouts 50 \
  --minimum-mixed-action-unions 8 \
  --minimum-calibrated-additions 8 \
  --minimum-games-with-additions 4 \
  --minimum-game-addition-rate-wilson-lower 0.10
```
