# FDAS PR99 retained-capacity transition model preregistration

Date: 2026-08-05

## Question and source boundary

PR99 asks whether the hierarchy frozen before PR98 can produce deterministic,
bounded shadow estimates of exact product effect and durable goal relief from
proposal-time retained-capacity features. It is a discovery fit, not a
calibration, validation, candidate-readout, gameplay, score, or win-rate test.

The only permitted source is the accepted PR98 report:

- cohort structural hash:
  `3c6203c6a7bd1512b026f0b66ae9dbfdae54c11d604d3343c06b4e4bfe1f5c8d`;
- query/episode dataset hash:
  `89eff1ca7b756bcbe47acf9a99e22b5a1f0f5da8fe34571457d78ace116c6eb1`;
- serialized report SHA-256:
  `be392866b5415a63667034c0c3f00711ea8384de0d8a37e7530ad48a7cf07e33`.

PR97 and all earlier diagnostic rows are forbidden. All 301 PR98 game ledger
entries and all 163 PR98 query rows must be accounted for exactly once. The
one right-censored row is retained with the exclusion reason
`right-censored-no-terminal-target` and does not enter target fitting.

## Frozen targets

Each of the 162 terminal rows maps to two nested binary outcomes:

| Terminal status | Exact product effect | Durable goal relief |
|---|---:|---:|
| `no-effect-observed` | 0 | 0 |
| `effect-without-goal-relief` | 1 | 0 |
| `goal-relief-observed` | 1 | 1 |

The controller-facing transition value is durable goal relief. Exact product
effect remains a separate lifecycle diagnostic and cannot substitute for goal
value.

## Frozen hierarchy

Only the 14 categorical fields in the proposal-time PR95 feature schema are
permitted. The ordered hierarchy is:

1. all 14 fields, identified by the exact PR95 feature signature;
2. `action_category`, `lifecycle_state`, `production_target`,
   `turn_phase_band`, and `completion_horizon_band`;
3. `action_category`, `lifecycle_state`, and `production_target`;
4. `action_category` and `lifecycle_state`.

Every observed bin is serialized with complete provenance. A bin is
sample-eligible only with at least 20 independent games. For a query, the
deepest sample-eligible matching level is selected. If that selected level's
interval is wider than `0.40`, the target abstains; interval width cannot
trigger a second, more favorable backoff. An unseen category backs off through
the same order. An unseen action/lifecycle root abstains.

## Frozen game-cluster estimator

Within a bin and target, every independent game contributes the mean of its
own terminal binary outcomes in that bin. The point estimate is the unweighted
mean of those per-game means, so multiple queries from one game do not create
pseudo-replication.

For every sample-eligible bin and target:

1. sort games by numeric seed and game ID;
2. initialize a separate Python `random.Random(980301)` stream;
3. draw exactly 10,000 bootstrap samples, each containing `n` games sampled
   with replacement from the bin's `n` games;
4. calculate the unweighted mean of the sampled per-game means;
5. sort the 10,000 estimates;
6. use zero-based order statistics `250` and `9750` as the deterministic 95%
   interval endpoints.

No interpolation, smoothing, cross-target sharing, production-target pooling,
feature selection, threshold search, retrospective level insertion, or
post-outcome feature is allowed. A bin below 20 games records provenance and
counts but exposes no point or interval estimate.

## Frozen artifact and prediction contract

The model must serialize:

- the exact source report, dataset, cohort, game, row, query, episode, feature,
  target, level, and outcome provenance;
- all 301 game ledger entries exactly once;
- all 162 fitted terminal rows exactly once and the one censored exclusion
  exactly once;
- per-bin raw rows, independent games, per-game target means, eligibility,
  point estimate, interval, width, and deterministic result hash;
- the ordered hierarchy, minimum games, bootstrap count and seed, maximum
  interval width, target definitions, and source hashes; and
- explicit false values for truth mutation, learning write-through, model
  calibration, candidate readout, policy, and action authority.

Typed model and prediction roundtrips must reject changed source lineage,
duplicate games or rows, invalid target nesting, changed intervals, tampered
hashes, forbidden features, reordered hierarchy, and authority leakage.

Two complete fits from the canonical PR98 JSON must be byte-identical. The
fit report may describe sample eligibility and numerical coverage on the
discovery rows, but it must label those values in-sample and must not report
them as calibration or predictive performance.

## Claim boundary and next gate

A passing PR99 fit establishes only deterministic construction and discovery
coverage for a shadow transition model. It does not establish out-of-sample
accuracy or authorize candidate readout.

The next scientific step must preregister a disjoint fixed confirmation cohort
and metrics before launch. Confirmation must independently pass PR98's
mechanics and diversity gates, preserve every seed in its denominator, and
evaluate the frozen PR99 model without refitting. Readout remains disabled
regardless of the PR99 in-sample result.
