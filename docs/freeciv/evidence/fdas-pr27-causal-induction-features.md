# FDAS PR27 causal defense induction features

Status: opt-in component implemented and regression-accepted; engine-live
discovery evidence pending; no induced-rule, readout, score, or gameplay claim.

## Motivation

PR26 showed that the `defense-episode-features/2.0` discovery set learned two
non-transferable associations. Exact `actor_unit_type=Musketeers` never
activated in 15 held-out episodes, while `city_size_band=1` activated four
times but worsened Brier score and calibration. Those proposals remain
demoted. Their train and holdout episodes are exhausted and cannot confirm a
replacement feature design.

## Versioned schema

`defense-episode-features/3.0` is an opt-in schema for a new discovery cycle.
It deliberately excludes exact actor type from the miner and records bounded,
cross-game context available at the authoritative pre-action revision:

- actor home-city relation, moves, and veteran bands;
- city disorder, size, and current production class;
- empire city-count and turn-phase lifecycle bands;
- operating-gold direction;
- total local units and already-fortified local redundancy; and
- explicitly visible enemy proximity and near-city count.

Visible-threat features preserve the epistemic boundary. `none-visible` means
only that the current player-visible enemy relation is empty; it is not global
enemy absence. If a visible enemy cannot be placed with complete topology and
coordinates, both proximity and near-city count become `unknown` rather than a
false safe value.

The prior `2.0` recorder and profiles remain unchanged. A new dedicated config
and manifest pair declares both the exact `3.0` schema and
`causal_episode_feature_schema=shadow-live`. The engine rejects unsupported
schema declarations or a `3.0` declaration without that capability. The live
auditor now verifies every eligible episode's recorded schema against its
activation source, preventing mixed-schema cohorts.

## Authority boundary

The new schema changes only durable episode context and quarantined induction
inputs. It does not alter the delayed 32-turn outcome definition, legacy
winner, FDAS bounded fortification contract, truth, policy authority, or
induced-rule readout. The first valid experiment must use fresh pinned seeds;
all PR24–PR26 games were inspected while selecting this design and are
ineligible for confirmation.

## Verification

- focused recorder, induction, activation, and auditor surface: `68 passed`;
- complete FDAS surface: `285 passed in 54.32s`;
- bounded city replay regenerated with `4` authorizations, `34` fallbacks,
  zero winner changes, and all gates passing;
- bounded defense replay regenerated with `13` authorizations, `25` fallbacks,
  zero winner changes, and all gates passing;
- Phase-0 generator reproduces semantic hash
  `beb5c88ecd312784da3129ade47c3dc948203d18bc05cf61299a2b5a23b08e07`;
- `git diff --check`: clean.

Engine-live collection remains a subsequent clean-source step. Any patterns
mined from that discovery population must still pass a separate untouched
held-out cohort and versioned promotion approval before they can leave
quarantine.
