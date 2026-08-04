# FDAS PR91 retained replacement-capacity queue evidence

Date: 2026-08-04

## Result

PR91 passes every preregistered mechanics and recurrence gate from clean commit
`b89287e420e6dacf0ba712ecf9974594d94c2a09`.

All 16 fixed fresh games reached turn 160, for 2,560 total engine turns. The
harness recorded 16 completed jobs, zero infrastructure failures, zero resumes,
and zero rejected engine actions. No reserve seed was used.

The strict aggregate audit accepted on two independent full passes. Both
passes produced structural hash
`a682210adeb4caad3d16295a17bfd257790c2d69dce59e111a09f78f391b46db`
and byte-identical report SHA-256
`cd57a34691eb272e343b9ee5d9a65d40d76c2b494f7a9a42c35796093e098b14`.

## Frozen cohort totals

| Measure | Result |
|---|---:|
| Fixed games | 16 |
| Shadow evaluations | 1,156 |
| No selected retained-queue match | 1,141 |
| Selected retained-queue matches | 15 |
| Ambiguous matches | 0 |
| Games with at least one selected match | 6 |
| Unique lifecycle registrations | 8 |
| Existing-queue observations | 8 |
| Authoritative product completions | 2 |
| Terminal queue divergences | 6 |
| Action-commit events | 0 |

The frozen recurrence threshold required selected matches in at least two
games; six games matched. The frozen outcome threshold required an exact
product in at least one game; two games completed products.

The 15 selected matches are evaluation-level observations, not 15 independent
operations. Repeated evaluations can select the same operation while its
lifecycle is already registered or after its deterministic identity has become
terminal. Registration is idempotent, so those evaluations produced eight
unique observers.

The two exact completions were:

- seed `111539`: Alpine Troops at city 110, proposed on turn 22 and observed as
  authoritative `unit:122` on turn 34;
- seed `111581`: Musketeers at city 114, proposed on turn 36 and observed as
  authoritative `unit:128` on turn 40.

The other six observers ended once with
`production-target-diverged-before-product-observation`; none churned through
repeated blocked events or expired after a known queue change. Proposals,
queue observations, product completions, and failures are one-to-one by
operation identity, and their counts match both live status and terminal-event
summaries.

## Descriptive rates

Selected retained queues occurred in 6/16 games (37.5%; Wilson 95% interval
18.5%–61.4%). Exact products occurred in 2/16 games (12.5%; 3.5%–36.0%). At
the lifecycle level, 2/8 observers completed a product (25%; 7.1%–59.1%).

These intervals describe mechanism yield only. Operations within a game are
not independent, and the cohort was not designed to estimate causal policy
value.

## What is established

- scalar PF selects already-authoritative grounded replacement-capacity queues
  in recurrent fresh games;
- an already-selected queue can be observed without submitting or crediting a
  production action;
- exact later product identities can be linked to the grounded operation;
- authoritative queue divergence is attributed immediately and exactly once;
- zero-yield games remain in the cohort denominator; and
- all parent FDAS mechanics, provenance, source-identity, and non-authority
  audits pass.

## Claim boundary and next target

PR91 does not establish that PF caused either queue selection, that a completed
unit relieved the source replacement-capacity deficit, or that score or win
rate improved. The six divergences also show that selection overlap alone is a
weak transition-value signal.

The next bounded slice should keep scalar PF and packets frozen and add exact
delayed relief attribution for the two terminal classes:

1. after a product completion, determine from later authoritative state whether
   the source-removal capacity deficit actually closed and remained closed for
   a fixed observation window;
2. label a queue divergence as realized no-progress, without treating the
   already-authoritative queue as an attempted action;
3. record route/lifecycle context for calibration, with repeated operation
   identities deduplicated; and
4. keep those labels shadow-only until a fresh held-out gate demonstrates that
   they improve decision-safe transition-value calibration.

The machine-readable audit is
`fdas-pr91-replacement-capacity-retained-queue.json`.
