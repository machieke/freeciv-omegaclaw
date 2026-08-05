# PR98 retained-capacity transition discovery cohort

Date: 2026-08-05

## Result

The fixed 301-game PR98 discovery cohort passes every mechanics and diversity
gate and is eligible for the separately preregistered PR99 shadow-model fit.
All 301 engine games completed from clean source commit
`8370d5102df62a7815b687fa3264f4ab8025b331`, with zero resume and zero
infrastructure failure. No seed was replaced, retried, or appended.

Two complete exports ran independently with four audit workers each. They are
byte-identical and both report:

- cohort structural hash:
  `3c6203c6a7bd1512b026f0b66ae9dbfdae54c11d604d3343c06b4e4bfe1f5c8d`;
- query/episode dataset hash:
  `89eff1ca7b756bcbe47acf9a99e22b5a1f0f5da8fe34571457d78ace116c6eb1`;
- serialized report SHA-256:
  `be392866b5415a63667034c0c3f00711ea8384de0d8a37e7530ad48a7cf07e33`.

All six cohort mechanics checks, all eight nested query/episode dataset gates,
and all eight preregistered diversity checks pass. Every parent PR95 audit
passes. Truth mutation and learning, readout, and policy authority remain
disabled.

## Discovery observations

| Measure | Count | Game rate (95% Wilson interval) |
|---|---:|---:|
| Games with a query | 121/301 | 40.2% (34.8% to 45.8%) |
| Terminal-bearing games | 120/301 | 39.9% (34.5% to 45.5%) |
| Right-censored-query-bearing games | 1/301 | 0.3% (0.1% to 1.9%) |
| `no-effect-observed`-bearing games | 83/301 | 27.6% (22.8% to 32.9%) |
| `effect-without-goal-relief`-bearing games | 30/301 | 10.0% (7.1% to 13.9%) |
| `goal-relief-observed`-bearing games | 31/301 | 10.3% (7.4% to 14.2%) |

The cohort produced 163 query rows. Exactly 162 reached a terminal episode
and one remained explicitly right-censored at the horizon; 180 zero-query
games remain in every rate denominator. Terminal episode counts are 97
no-effect, 32 exact effects without durable relief, and 33 durable goal-relief
observations. These statuses occur in 83, 30, and 31 independent games,
respectively. The 120 terminal-bearing games and all three status partitions
comfortably exceed the frozen minima of 20 terminal-bearing games, 30 terminal
episodes, and 10 episodes plus 10 independent games per status.

The proposal-time data contain 68 exact categorical feature signatures. PR99
must use only those frozen features and the preregistered hierarchy; the
terminal status, observation timing, score, candidate readout, and other
future information remain forbidden inputs.

## Reproducibility

The two audit invocations independently replayed the complete corrected PR95
chain for all 301 games, joined every proposal-time query to at most one exact
terminal episode, retained the censored row, and serialized with canonical
JSON. Literal file comparison and SHA-256 comparison both pass.

The versioned JSON report is one of those two identical outputs. It retains
the complete game ledger, parent hashes, query rows, feature signatures,
checks, rates, and authority flags.

## Claim boundary and next gate

PR98 establishes discovery-data mechanics and diversity adequacy only. It
does not establish calibration, transition-value accuracy, causal action
value, candidate-readout safety, gameplay improvement, score improvement, or
win rate.

PR99 may now fit the frozen deterministic, game-clustered, shadow-only model
on PR98 rows. It must reproduce byte-identically, abstain whenever the selected
95% interval is wider than `0.40`, preserve complete provenance, and keep all
authority disabled. A disjoint preregistered confirmation cohort remains
mandatory before any candidate readout can consume a predicted value.
