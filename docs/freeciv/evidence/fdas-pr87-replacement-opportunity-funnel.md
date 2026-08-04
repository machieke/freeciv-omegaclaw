# FDAS PR87 replacement-opportunity funnel result

Date: 2026-08-04

## Result

Accepted. The fixed 16-game cohort completed from clean source commit
`fb4781798591fca850ba4dad14c4ba08f87022da` with zero infrastructure
failures, zero resumes, zero rejected engine actions, and 616,718 valid event
rows. All five aggregate acceptance gates and every game-level
lifecycle/readout/funnel audit pass.

The deterministic report has structural hash
`9f66e977e9e0bd370de718cc8b4b18e6527313a4787030cd3937f414242e66eb`
and file SHA-256
`8a89b5c6da575a7865b175b5731b795e0ae252fa43dab3c06d4fffd058ef1d28`.
A full second audit of the 1.2 GB artifact tree produced a byte-identical
report.

## Opportunity funnel

The 1,437 revision-level evaluations partition exactly:

| First stage | Revisions | Share |
|---|---:|---:|
| `no-safe-replacement-relation` | 819 | 57.0% |
| `no-deficit-target-city` | 472 | 32.8% |
| `current-candidate-not-grounded` | 79 | 5.5% |
| `grounded-pair-available` | 67 | 4.7% |

All 16 games encountered `no-safe-replacement-relation`; 10 of 16 games also
grounded at least one safe pair. The 819 dominant-blocker revisions contained
1,080 deficit-target observations, 1,599 critical-source-garrison
observations, 2,081 reinforcement-route observations, and zero safe
replacement relations. This isolates the dominant loss upstream of lifecycle
materialization and readout: the exact relation that identifies a source-safe
replacement defender is unavailable.

The smaller 79-revision downstream blocker contained 322 structural joins and
322 materialized replacement candidates, all rejected by the current readout.
A supplementary post-hoc ledger drilldown (not a preregistered acceptance
metric) partitions its 322 candidate rejections as:

- 107 `active-lifecycle-unavailable`;
- 96 `route-attempt-budget-mismatch`;
- 60 `current-step-not-reservable`; and
- 59 `replacement-route-invalid`.

This downstream lifecycle/route freshness issue is real but secondary in
frequency to relation availability.

## Interpretation

PR87 validates the why-not instrumentation and confirms the PR86b diagnosis on
fresh games. The next bounded implementation target should increase the yield
of exact, source-safe replacement relations. It must preserve the invariant
that moving the reinforcement actor never leaves its source city below the
ruleset-grounded garrison requirement. Broadening readout or retuning flow
before solving that upstream constraint would address at most the smaller
5.5% stage.

A subsequent treatment still requires its own clean preregistration and fresh
cohort. PR87 itself authorizes no candidate, action, transition value, policy,
score, or win-rate claim.

## Evidence

- Aggregate audit:
  `fdas-pr87-replacement-opportunity-funnel.json`
- Preregistration:
  `fdas-pr87-replacement-opportunity-funnel-preregistration.md`
- Immutable local artifact root:
  `artifacts/freeciv/fdas-pr87-replacement-opportunity-funnel-v1`
- Run-summary SHA-256:
  `d0a380897c04522ed13982f49cb41e426f6f3221c1c7a89d9cdb2a4b8cae7531`
