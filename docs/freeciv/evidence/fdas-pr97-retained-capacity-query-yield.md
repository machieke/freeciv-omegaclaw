# PR97 retained-capacity query-enabled yield pilot

Date: 2026-08-04

## Result

The fixed 64-game PR97 pilot passes after the separately documented narrow
audit correction for one valid multi-operation refresh interleaving. All 64
engine games completed from clean source commit
`a55e71b8919d218c624595d5abc880cf9cd27dd0`, with zero resume and zero
infrastructure failure. No seed was replaced, retried, or appended.

Both complete corrected audits pass and are byte-identical.

- Cohort structural hash:
  `3bf6e8297bf0fed31666efb718c60d29c240938c3cf982e66dcc5678ee29f245`
- Query/episode dataset hash:
  `39410d05b426eb660ddba0032806ed8fe9a70ee662579cba8075da5199e36d9c`
- Serialized report SHA-256:
  `a45b7a2e5239bdf5126f97bed58f1f07cf36a363994e55b9e6ae5f010a7ec541`

All six pilot gates and all eight nested PR96 dataset gates pass. All 64 parent
PR95 audits pass under the corrected audit contract; there are no extraction,
identity, source, terminal-partition, censoring-partition, or authority errors.

## Fresh yield

| Measure | Count | Game rate (95% Wilson interval) |
|---|---:|---:|
| Games with a query | 18/64 | 28.1% (18.6% to 40.1%) |
| Terminal-bearing games | 18/64 | 28.1% (18.6% to 40.1%) |
| Right-censored-query-bearing games | 0/64 | 0.0% (0.0% to 5.7%) |
| `no-effect-observed`-bearing games | 12/64 | 18.8% (11.1% to 30.0%) |
| `effect-without-goal-relief`-bearing games | 3/64 | 4.7% (1.6% to 12.9%) |
| `goal-relief-observed`-bearing games | 6/64 | 9.4% (4.4% to 19.0%) |

The 18 contributing games produced 24 exact queries and 24 terminal episodes;
46 games had no query. Episode counts are 14 no-effect, four exact effects
without durable relief, and six durable goal-relief observations. Every query
reached a terminal outcome within the 160-turn horizon, so the censored count
is zero. This does not mean censoring was suppressed: the Wilson upper bound
for a censor-bearing game remains 5.7%, and the typed censored path remains
covered by PR96 tests.

The dataset retains 20 exact categorical feature signatures. Production
targets include Musketeers, Riflemen, and Alpine Troops; no feature group is
pooled or simplified retrospectively.

## Updated prospective sizing

The exact binomial planner uses status-bearing games, not episode counts. For
a 90% probability of observing at least 10 status-bearing games:

| Status | Plug-in fixed games | 95% Wilson-lower sensitivity |
|---|---:|---:|
| `no-effect-observed` | 74 | 126 |
| `effect-without-goal-relief` | 301 | 882 |
| `goal-relief-observed` | 149 | 323 |

The rare effect-without-relief status remains limiting. Its fresh plug-in rate
is 4.7%, below the reused PR94 6.25% rate, so the provisional fixed size for
each future discovery or confirmation cohort increases from 225 to 301 games.
The lower-bound sensitivity falls from 1,275 to 882 because 64 fresh games
narrow the interval despite the lower point estimate.

PR97 rows remain excluded from model fitting and confirmation. A later
discovery and confirmation must each use separate, fixed, disjoint seeds and
must independently satisfy the PR94 30-episode, 20-contributing-game, and
10-per-status gates.

## Initial rejection and correction

The first two aggregate passes were also byte-identical but rejected because
seed `130553` contained two concurrent retained queues. One queue terminally
diverged, the other was revalidated, and the following FDAS revision was
parented by that revalidation. The original audit required the terminal to be
the revision chain's direct parent.

Commit `16a79c7` adds only the exact two-parent, same-turn, typed retained-queue
interleaving. It does not perform a broad ancestor search. Wrong history,
mechanism, turn, parent count, operation, and cycle cases remain rejected. The
engine evidence and every outcome are unchanged. See
`fdas-pr97-interleaved-retained-queue-audit-correction.md`.

## Claim boundary and next gate

PR97 establishes fresh query, terminal, status, and feature recurrence and a
revised prospective evidence-yield plan. It does not fit or validate a model,
establish transition value or causality, alter the controller, or support a
gameplay, score, or win-rate claim.

The next bounded target is a separately preregistered 301-game discovery
cohort, or an explicitly justified design change that improves rare-status
yield before opening that cohort. Confirmation must remain disjoint and cannot
be sized or interpreted from discovery outcomes after it starts.
