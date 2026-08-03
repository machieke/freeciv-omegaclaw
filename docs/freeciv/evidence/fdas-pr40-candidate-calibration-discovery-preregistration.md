# FDAS PR40 candidate-calibration discovery preregistration

Status: frozen before engine execution; discovery-only and non-authorizing.

## Purpose and exclusions

PR38 established that the corrected defense choice surface yields both exact
action families and delayed selected outcomes. PR39 implemented the typed,
lineage-aware calibration artifact. This fresh cohort is the first data that
may be used to fit that artifact.

PR34 through PR38 and every engineering smoke are excluded from fitting and
confirmation. The seeds in this document are discovery-only and will be
excluded from later holdout confirmation. Nonselected alternatives remain
censored and are never interpreted as failed actions or counterfactual
outcomes.

## Frozen design

| Field | Declaration |
|---|---|
| Discovery ID | `fdas_candidate_calibration_discovery_v1` |
| Backend | `engine-live` |
| Ruleset | `civ2civ3` |
| Horizon | 160 turns |
| Condition | `e_full_loop` only |
| Seeds | `104851`, `104869`, `104879`, `104891`, `104911`, `104917`, `104933`, `104947`, `104953`, `104959` |
| Source | one identical clean commit after this preregistration |
| Model | `qwen3-coder-next:latest`, temperature 0, thinking disabled |
| FDAS profile | `fdas_manifest_defense_choice_surface_shadow.json` |
| Surface | exact legal, unambiguous move/fortify action bindings |
| Outcome | 32-turn selected-actor city-defense persistence v2 |
| Lineage | deterministic game + participants + target + action stratum |
| Resume/workers | disabled; one serial worker |
| Fit | separate action strata; lifecycle backoff only within action |
| Minimum fit support | five action lineages; three lifecycle lineages |

The disjoint seeds `104971`, `104987`, `104999`, `105019`, `105023`,
`105031`, `105037`, and `105071` are reserved for a later confirmation
design and must not be inspected or used during discovery.

## Mechanical gates

All ten games must complete the horizon without infrastructure failure or
rejected actions. Every event ledger must validate without errors or warnings.
All source identities must be identical and clean. Choice stores must be
independent, current, non-quarantined, outcome-free, selected-only, explicitly
censored for alternatives, and non-authorizing. Every candidate must carry a
durable lineage. The exact surface, action families, and outcome target must
match the manifest.

## Frozen progression gates

All must pass before the artifact may be fit:

- at least 40 observed selected outcomes;
- at least eight positive and eight negative outcomes;
- at least 12 multi-candidate sets;
- at least ten mixed move/fortify sets;
- at least five selected actions in each action stratum;
- at least five selected durable lineages per action stratum;
- at least five observed durable lineages per action stratum; and
- at least ten distinct selected actor/context signatures.

Failure stops fitting. Do not lower thresholds, extend this cohort, pool prior
data, change policies, or choose a different grouping after seeing outcomes.
A passing discovery gate permits an in-sample descriptive model only. It does
not establish out-of-sample calibration, counterfactual validity, candidate
ranking safety, gameplay impact, score improvement, or win rate.

## Frozen execution

```bash
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_choice_surface_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_choice_surface_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-candidate-calibration-discovery-v1 \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 12 --limit-seeds 10 --condition e_full_loop \
  --main-only --no-resume
```

Frozen fit invocation:

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/fit_fdas_candidate_calibration.py \
  artifacts/freeciv/fdas-candidate-calibration-discovery-v1 \
  --output docs/freeciv/evidence/fdas-pr40-candidate-calibration-discovery.json \
  --discovery-id fdas_candidate_calibration_discovery_v1 \
  --model-id fdas-defense-action-lifecycle-calibration-discovery-v1 \
  --expected-seed 104851 --expected-seed 104869 \
  --expected-seed 104879 --expected-seed 104891 \
  --expected-seed 104911 --expected-seed 104917 \
  --expected-seed 104933 --expected-seed 104947 \
  --expected-seed 104953 --expected-seed 104959 \
  --minimum-action-lineages 5 \
  --minimum-lifecycle-lineages 3 \
  --minimum-observed-selected-outcomes 40 \
  --minimum-observed-each-outcome 8 \
  --minimum-multi-candidate-sets 12 \
  --minimum-mixed-operation-type-sets 10 \
  --minimum-selected-each-operation-type 5 \
  --minimum-selected-operation-type-lineages 5 \
  --minimum-observed-operation-type-lineages 5 \
  --minimum-actor-context-signatures 10
```
