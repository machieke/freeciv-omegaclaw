# FDAS PR39 lineage-aware candidate calibration artifact

## Scope

PR39 implements the non-authorizing artifact permitted by the passing PR38
yield gate. It does not fit PR38 data and does not enable candidate ranking.

Every newly recorded candidate now carries a deterministic game-local
`(participants, target, operation type)` lineage. Sequential route steps may
remain descriptive rows, but the calibration fit collapses them to one
effective lineage contribution. Selected-only exports bind that lineage to
the exact action stratum and retain all nonselected alternatives as censored.

The typed calibration model estimates the 32-turn selected-actor city-defense
persistence outcome separately for garrison moves and fortification. It uses
Wilson 95% intervals over effective lineages, prefers a supported
action/lifecycle bin, backs off to the action-level bin, and abstains when the
frozen minimum lineage support is absent. Every export, bin, model, and
prediction has a recomputed semantic hash. Models and predictions explicitly
declare truth, readout, and policy authority false.

The fitting tool first reruns the source, event-ledger, censorship, action
stratum, outcome-contrast, and lineage gates over a preregistered discovery
cohort. It refuses to fit if either the mechanical or progression gate fails,
if stores overlap or are quarantined, if episodes overlap, or if durable
candidate lineage is missing.

## Tests

The focused calibration and episode suite passes 25 tests. It covers:

- stable lineage identity across route-step operation IDs;
- selected-only lineage provenance;
- cluster-effective sample size and fractional lineage outcome mass;
- lifecycle-specific estimates and action-level backoff;
- insufficient-support abstention;
- non-authority declarations and deterministic round trip;
- semantic tamper rejection; and
- source, episode, and lineage overlap rejection.

## Claim boundary

This is an implementation and safety result only. No fresh discovery data has
yet been collected, no model has been fit, and no holdout has tested
calibration, candidate recall, decision safety, gameplay impact, score, or win
rate. PR34 through PR38 remain excluded from later fitting and confirmation.
