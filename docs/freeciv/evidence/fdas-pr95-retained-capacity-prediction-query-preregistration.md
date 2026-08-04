# FDAS PR95 retained-capacity prediction-query preregistration

Date: 2026-08-04

## Question

PR94 found that the existing seven retained-capacity episodes are insufficient
for transition-value fitting or confirmation. PR95 asks whether the controller
can capture a stable, proposal-time feature query for future calibration while
continuing to abstain from numerical prediction and preserving all PR93
learning/readout isolation.

## Frozen component

Add a separate shadow-live
`replacement_capacity_transition_prediction_query` component. Exactly one
query is opened with each retained-capacity outcome label, from the same exact
proposal snapshot and current FDAS revision, before product or terminal outcome
observation.

The query status is always `abstained` in PR95, with reason
`insufficient-independent-calibration-evidence`. It has no estimate, interval,
model ID, prediction authority, episode prediction link, conductance update,
induction input, or candidate-readout effect.

## Frozen feature schema

Schema `retained-capacity-transition-features/1.0` contains only information
available at proposal time:

- action category: `city_production`;
- lifecycle state: `retained-authoritative-queue`;
- normalized production target name;
- turn phase band: `0-39`, `40-79`, or `80+`;
- completion horizon band from deadline minus proposal turn: `1-16`, `17-32`,
  `33-64`, or `65+`;
- source and target city size bands: `1`, `2-4`, `5-8`, or `9+`;
- source city food-surplus and shield-surplus bands: `negative`, `zero`,
  `1-4`, or `5+`;
- source and target own-unit count bands: `0`, `1`, `2`, or `3+`;
- source city disorder: `true`, `false`, or `unknown`;
- exact-queue match: `true`; and
- cross-city deficit: `true`.

Raw changing numeric values remain in the authoritative snapshot and do not
enter symbolic atom arguments. The categorical query records the exact
snapshot ID, revision ID, deficit atom, operation, proposal event, target
label, and a deterministic feature/result hash.

## Persistence and events

Queries use a separate atomic, manifest/attempt/game-bound store. Corrupt,
wrong-identity, duplicate-operation, or hash-invalid stores quarantine and fail
startup. One typed `transition_prediction_abstained` event is emitted causally
from the retained-queue proposal/label-open event. Counters must agree across
the store, events, status, and terminal summary.

Restart recovery must load proposal-time queries without recomputing them from
a later snapshot and emit at most one event per query.

## Acceptance criteria

- feature construction is deterministic and uses only proposal-time state;
- missing source/target city, mismatched snapshot/revision, malformed proposal,
  or absent deficit atom fails closed;
- exact bands and normalization have boundary tests;
- store round-trip is byte-identical and corruption quarantines;
- duplicate replay is idempotent and a changed query collides;
- every query is abstained with all numerical/model fields absent;
- PR93 episode prediction IDs remain empty;
- no query appears in the main episode, learning, induction, conductance, or
  readout stores;
- manifest, event, causal, digest, counter, and restart audits pass; and
- a fresh fixed-seed engine smoke observes at least one query and its later
  terminal episode without any authority change.

## Claim boundary

A pass establishes only proposal-time, outcome-blind feature capture and
abstention mechanics. It does not estimate transition value, fit or validate a
model, change action selection, or claim gameplay, score, or win-rate value.
