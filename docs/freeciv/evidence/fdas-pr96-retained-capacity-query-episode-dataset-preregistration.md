# FDAS PR96 retained-capacity query/episode dataset preregistration

Date: 2026-08-04

## Question

PR95 proved that one outcome-blind transition query can be frozen when a
retained-capacity operation is proposed, but it did not define the later
training row. PR96 asks whether those proposal-time queries can be joined
losslessly to terminal PR93 episodes while preserving queries whose outcomes
are not yet observable as right-censored evidence.

This is a dataset-mechanics and evidence-planning exercise. It does not fit a
model, infer a value for a censored row, change readout, or authorize an action.

## Frozen source evidence

The first mechanics audit uses only the clean PR95 smoke:

- artifact root:
  `artifacts/freeciv/fdas-pr95-retained-capacity-transition-query-smoke-v1`;
- source commit: `600267555b6ad86a92effa1d9bf23bcf5db39e30`;
- seed: `111539`;
- parent query-audit structural hash:
  `50db864724479095fdde65996ff0cac8bbd446f3b08a57cd6fcbeff6e9415294`.

This reused one-game smoke may prove join mechanics only. It is not a
discovery, calibration, confirmation, effectiveness, or population-rate
cohort.

## Frozen row and join semantics

The dataset contains one row per retained-capacity transition query. A row is
identified by the exact game, player, operation, label, and query identities.
The join must require:

1. exactly one typed, digest-valid query per operation and label;
2. exact game, player, operation, label, proposal event, snapshot, and
   proposal-revision agreement;
3. a query that is still the PR95 abstention, with no estimate, interval,
   model, truth, learning, transition-value, readout, policy, or action
   authority;
4. at most one typed PR93 terminal episode with the same game, player,
   operation, and `observed_delta.label_id`;
5. exact agreement between the episode's before revision and the query's
   proposal revision, and between its proposal provenance and the query's
   proposal event;
6. an after revision distinct from the before revision for every terminal row;
7. empty episode prediction IDs and no execution-event assertion; and
8. deterministic row identity, row hash, ordering, and dataset hash.

A query with no terminal episode is retained as `right-censored`. Its outcome
status, episode ID, observed turn, after revision, and realized effects/relief
remain absent. Censoring is never encoded as `no-effect-observed`. A terminal
episode without a query, duplicate query/episode binding, ambiguous join, or
identity mismatch fails the export.

Every fixed game remains in the dataset, including zero-query games. A game
with no query is represented in the game ledger, not by manufacturing a row.

## Frozen summaries and mechanics gates

The exporter reports:

- fixed games, games with queries, and zero-query games;
- query rows, terminal rows, and right-censored rows;
- the three terminal status counts;
- feature-signature counts using only the frozen PR95 categorical schema;
- exact source commits and parent audit hashes; and
- unique game, seed, operation, label, query, episode, and row identities.

Mechanics pass only when every source is clean and exact-commit-bound, every
parent audit passes, all fixed games are retained once, every query is joined
exactly once, every terminal episode is consumed exactly once, the terminal
and censored partition is complete, and a second export is byte-identical.

## Frozen evidence-yield planning

No unseen query-enabled cohort has yet been measured, so initial planning uses
only the already published PR94 16-game outcome cohort. To avoid treating
multiple outcomes in one game as independent, a game contributes at most one
occurrence to each status for planning. The observed status-bearing game rates
are:

| Terminal status | Games | Plug-in rate |
|---|---:|---:|
| `no-effect-observed` | 3/16 | 18.75% |
| `effect-without-goal-relief` | 1/16 | 6.25% |
| `goal-relief-observed` | 2/16 | 12.50% |

For a fixed cohort of `n` independent games and a frozen per-game occurrence
probability `p`, the planner computes the exact binomial probability of at
least 10 status-bearing games. The smallest `n` reaching 90% under the plug-in
rates is respectively 74, 225, and 111 games. The rare
`effect-without-goal-relief` status therefore sets a provisional minimum of
225 games for each independently declared discovery or confirmation cohort.

The planner must also disclose sensitivity to the lower endpoint of each 95%
Wilson interval. Those lower endpoints imply 213, 1,275, and 404 games,
respectively, for the same 90% yield probability. This sensitivity is a
warning about rate uncertainty, not permission to claim that 225 games are
guaranteed adequate.

Before a 225-game discovery launch, run one fixed 64-game query-enabled yield
pilot on previously unused seeds. It is mechanics/yield evidence only and
cannot enter model fitting or confirmation. All 64 games, zero-query games,
terminal rows, and censored rows remain in its report. After it completes, a
new preregistration may replace the provisional rate with its fixed-cohort
rate and interval; it may increase or decrease a future cohort only before
that cohort's seeds are declared. It may not append seeds to rescue an already
opened discovery or confirmation cohort.

Discovery and confirmation must use disjoint fixed seeds and source artifacts.
Each must independently meet the existing PR94 minimums of 30 terminal
episodes, 20 games with an episode, and 10 episodes in every terminal status.
No query from the 64-game yield pilot or reused PR92/PR95 evidence can satisfy
those gates.

## Acceptance criteria

- a pure typed join accepts exact terminal and right-censored rows;
- synthetic tests reject every identity, revision, proposal, status,
  authority, duplication, and orphan-episode violation above;
- a cohort exporter composes the complete PR95 live audit for every game;
- zero-query games and censored queries are preserved explicitly;
- the PR95 mechanics smoke exports twice byte-identically;
- an exact deterministic binomial planner reproduces the frozen 74/225/111
  plug-in and 213/1,275/404 Wilson-lower sample sizes; and
- fitting, calibration, learning, readout, conductance, policy, and action
  authority remain disabled.

## Claim boundary

A pass establishes only deterministic, outcome-safe query/episode joining and
a reproducible evidence-yield plan. The one-game mechanics row and the reused
PR94 rates do not estimate transition value, validate calibration, establish
causality, improve gameplay, or support a score or win-rate claim.
