# PR95 retained-capacity proposal-time transition queries

## Result

The clean fixed-seed engine smoke confirms outcome-blind proposal-time feature
capture for retained-capacity operations. One exact query was captured at turn
22 and its later terminal outcome produced one common PR93 episode. The query
explicitly abstained from numerical prediction because PR94 did not meet the
frozen evidence-adequacy gate.

The run completed one of one games with no infrastructure failure or resume.
All ten strict audit gates pass twice byte-identically.

## Captured query

The query records the exact proposal event, snapshot, FDAS revision, operation,
outcome-label identity, and deficit atom. Its categorical proposal-time feature
values were:

- action category: `city_production`;
- lifecycle: `retained-authoritative-queue`;
- production target: `alpine troops`;
- turn phase: `0-39`;
- completion horizon: `33-64`;
- source city size: `2-4`;
- target city size: `1`;
- source food surplus: `1-4`;
- source shield surplus: `5+`;
- source own units: `1`;
- target own units: `0`;
- source disorder: `false`;
- exact queue match: `true`; and
- cross-city deficit: `true`.

Its status is `abstained`, reason is
`insufficient-independent-calibration-evidence`, and estimate, interval, and
model identity are all absent. It has false truth, learning, transition-value,
readout, policy, and action-selection authority.

## Engine evidence

- Artifact:
  `artifacts/freeciv/fdas-pr95-retained-capacity-transition-query-smoke-v1`
- Seed: `111539`
- Horizon: 160 turns
- Source commit: `600267555b6ad86a92effa1d9bf23bcf5db39e30`
- Source dirty: `false`
- Games complete: 1/1
- Infrastructure failures: 0
- Resumed: 0
- Queries captured: 1
- Queries abstained: 1
- Terminal retained-capacity episodes: 1

## Strict audit

The audit composes the complete PR93 episode audit and then verifies:

1. the exact manifest abstention contract;
2. the separate typed, identity-bound, non-quarantined query store;
3. one query per opened retained-capacity label;
4. exact recomputation through the production builder using the recorded
   proposal-time `state_snapshot` event;
5. one causal, revision-bound, non-authorizing abstention event per query;
6. incremental event digests replaying to the final store;
7. exact event/store/status/terminal counters;
8. no query link in episode prediction IDs, the main learning store, induction,
   or readout events; and
9. agreement between the final store and final query-event digest.

The live audit passed twice byte-identically:

- Structural hash:
  `50db864724479095fdde65996ff0cac8bbd446f3b08a57cd6fcbeff6e9415294`
- File SHA-256:
  `6cf310f1bd6cb31b27d249608aeda5ca04cf9856fd1706fabffb2c72d85a358e`

The machine-readable report is
`docs/freeciv/evidence/fdas-pr95-retained-capacity-transition-query.json`.

## Validation

The component, runtime, manifest, event-schema, and feature-band suite passed
135 tests. The live auditor additionally replayed the exact engine evidence
twice.

## Next bounded target

Extend the PR94 dataset exporter to join these frozen proposal-time queries to
their later terminal episodes. Then define a fresh discovery/confirmation
cohort power plan based on observed query yield and the rare
`effect-without-goal-relief` status. Do not fit or activate a numerical model
until the existing 30/20/10-per-status adequacy gates and disjoint-cohort gate
are satisfied.
