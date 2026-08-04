# PR96 retained-capacity query/episode dataset and yield plan

Date: 2026-08-04

## Result

PR96 passes the preregistered mechanics gates. The typed dataset row joins an
exact PR95 proposal-time query to at most one later PR93 terminal episode. A
query without an episode is represented as `right-censored`; it is never
converted into a negative outcome. Orphan episodes, duplicate bindings,
identity or revision disagreement, proposal-provenance disagreement,
prediction links, execution assertions, and authority-bearing records fail
closed.

The implementation is split into three independently testable pieces:

- `FdasRetainedCapacityQueryEpisodeRow` and
  `join_retained_capacity_transition_queries` implement the pure typed join;
- `export_fdas_retained_capacity_query_episode_dataset` composes the complete
  PR95 live audit for every fixed game and retains zero-query games; and
- `retained_capacity_evidence_yield_plan` computes exact fixed-cohort
  binomial yield sizes from the already published PR94 per-game recurrence.

No numerical model was fitted and no learning, readout, conductance, policy,
or action authority was enabled.

## Engine-backed mechanics evidence

The frozen PR95 seed-111539 smoke was exported twice from source commit
`600267555b6ad86a92effa1d9bf23bcf5db39e30`. Both exports are byte-identical.

- Parent PR95 audit hash:
  `50db864724479095fdde65996ff0cac8bbd446f3b08a57cd6fcbeff6e9415294`
- Dataset hash:
  `9ae738c57dad51b1be98afefca4bf6de181d9c25b7f64dfe57dcbdd23ad655dd`
- Serialized report SHA-256:
  `f73305fb5dfef01b9041c3b8d640f3f320fdbc1a54d4d0f4f33b5787504a51dd`
- Fixed games / games with queries: `1 / 1`
- Query / terminal / right-censored rows: `1 / 1 / 0`
- Terminal status: one `goal-relief-observed`
- Extraction errors: `0`

All eight mechanics gates pass: fixed-game retention, composed parent-audit
acceptance, clean source binding, expected parent hash, exact terminal/censor
partition, complete terminal-status partition, unique identities, and zero
extraction errors. The exact feature group is retained in
`fdas-pr96-retained-capacity-query-episode-dataset.json`.

The smoke has no censored row because its one query reached a terminal outcome.
The focused synthetic suite separately proves the censored branch and rejects
orphan, duplicate, identity, revision, prediction, and authority violations.

## Evidence-yield plan

The exact planner treats a game, not an episode, as the independence unit and
allows at most one occurrence of each status per game. From the published PR94
cohort, the status-bearing game counts are 3/16 no-effect, 1/16 effect without
relief, and 2/16 goal relief.

| Status | Plug-in games for 90% chance of at least 10 | 95% Wilson-lower sensitivity |
|---|---:|---:|
| `no-effect-observed` | 74 | 213 |
| `effect-without-goal-relief` | 225 | 1,275 |
| `goal-relief-observed` | 111 | 404 |

The rare middle status sets the provisional size at 225 games for each future
discovery or confirmation cohort. The 1,275-game sensitivity quantifies how
uncertain that provisional estimate remains; it is not hidden or treated as a
guarantee. A fixed 64-game query-enabled yield pilot must run first on unused
seeds, and none of its rows may enter discovery fitting or confirmation.

The deterministic plan hash is
`ad107a7c690e17c4823d6a5fc7af415cdf2eca0e1d39e09f3c0d1a0f75cc1701`;
its serialized SHA-256 is
`5654aefa6dc3d798d5ed7ca6d33e6aea1ef087606a0ae0af3b739fa9fec05c32`.

## Verification

The focused component and planning suite passes 45 tests. It includes exact
terminal and censored round-trips, every join rejection above, binomial
minimality, frozen sample-size reproduction, input validation, and mandatory
authority isolation. Both the engine-backed dataset and numerical yield plan
serialize byte-identically on a second pass.

## Claim boundary and next gate

PR96 establishes deterministic outcome-safe dataset mechanics and a
reproducible evidence-yield plan only. It does not estimate transition value,
validate calibration, establish causality, improve policy, or support a score
or win-rate claim.

The next bounded target is to preregister and launch the fixed 64-game
query-enabled yield pilot with previously unused seeds. Its only scientific
outputs are query recurrence, terminal/censoring yield, status-bearing game
rates, and updated prospective sample-size sensitivity.
