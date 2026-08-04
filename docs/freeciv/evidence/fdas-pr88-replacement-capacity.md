# FDAS PR88 replacement-capacity demand result

Date: 2026-08-04

## Result

Accepted. All 16 fixed games completed from clean source commit
`f29aa33726aa5022ff03eba2efa8c90918516621` with zero infrastructure
failures, zero resumes, zero rejected engine actions, and 508,854 valid event
rows. Every game-level lifecycle, candidate-readout, opportunity-funnel, and
capacity-demand audit passes.

The deterministic report has structural hash
`56f89987aa1b544450d62cff2b01519850d2ade1bcc48225a5431be0e833229f`
and file SHA-256
`d148394cae38b8dde11d54253dd1bfdfae912a0dbb979a601a27e5133b349257`.
A full second audit of the approximately 1.0 GB artifact tree produced a
byte-identical report with the same SHA-256.

## Capacity demand and candidate recall

Across 1,037 current-revision shadow evaluations, the gated projector emitted:

| Evidence | Count | Games with evidence |
|---|---:|---:|
| `city-replacement-capacity-deficit` goals | 1,789 | 16/16 |
| legal persistent-defender production candidates | 2,837 | 16/16 |

Every candidate is byte-identical to a current legal `city_production` action,
targets the source city named by the capacity deficit, selects a
ruleset-grounded persistent defender, has a deterministic candidate hash, and
remains `authority_eligible=false`. The existing source-garrison removal
invariant was not relaxed, and planned production was never projected as
current factual coverage.

This confirms the PR87 replay diagnosis on fresh games: spare-defender capacity
is a broad, live bottleneck rather than an isolated fixture condition. The
mechanism appears in every fixed game without any frequency-based acceptance
gate.

## Next blocker

All 2,837 candidates were shadow-rejected with the single explicit blocker
`uncompiled-action-effect`. This is a useful downstream boundary, not an
engine-action failure. The proxy action schema proves current legality but
intentionally leaves generic `city_production` effect semantics unknown. PR88
therefore recalls the correct legal action surface but cannot yet route those
candidates through the pressure schedule as a causal defender-production
operation.

The next bounded implementation should add a capacity-specific production
operation with:

- exact immediate semantics for setting the source-city queue to the selected
  persistent defender;
- a ruleset-grounded production ETA and explicit delayed completion predicate;
- source production-slot, treasury, food, population, and active-operation
  requirements;
- no claim that queue selection equals completed replacement capacity; and
- shadow-only scheduling and outcome observation before any authority study.

It should not mark generic `city_production` effects as universally known or
change action selection. A subsequent treatment requires its own clean
preregistration and fresh paired outcome cohort.

## Claim boundary

PR88 establishes exact live representation and legal shadow recall of the
source-city replacement-capacity bottleneck. It does not establish production
completion, a safe replacement relation, transition value, preference, action,
score, or win-rate improvement.

## Evidence

- Aggregate audit: `fdas-pr88-replacement-capacity.json`
- Preregistration: `fdas-pr88-replacement-capacity-preregistration.md`
- Immutable local artifact root:
  `artifacts/freeciv/fdas-pr88-replacement-capacity-v1`
- Run-summary SHA-256:
  `6e3af9cd6a0919841c7b972ccad12913164981cb7970493158eff1d6be560b68`
