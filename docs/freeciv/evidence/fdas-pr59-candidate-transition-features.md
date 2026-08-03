# FDAS PR59 grounded candidate-transition features

## Result

PR58's clean engine smoke exposed two genuine in-slice reinforcement choices,
but the frozen calibration model assigned every candidate in each set the same
lifecycle-level estimate and broad interval. Inspection showed that the
outcome-free query did not record the native route or source-unit facts that
distinguished those candidates. Relaxing PR58's uncertainty gate would not
repair this information loss.

PR59 adds a separate observational feature projection for reinforcement moves.
It preserves the original query ID and causal episode features, and appends:

- actor HP band and exact ruleset unit type;
- native estimated-turn, first-step-cost, total-cost, and path-length bands;
- whether the actor starts in the target city, another own city, or no city;
- counts of other own and fortified units on the source tile; and
- an explicit transition-grounding status.

The projection accepts only the bounded city-garrison move operation. It binds
route facts to the exact snapshot turn and a non-future source sequence, checks
actor,
origin, movement points, transport state, action cost, and first-step tile, and
never imputes a missing value. A missing, unreachable, stale, or action-
inconsistent route produces a fixed reason plus `unknown` mechanical features.

## Authority and compatibility boundary

This is collection substrate, not a model or policy change. The frozen PR40
action/lifecycle model ignores the added schema and produces byte-identical
predictions for an enriched query. PR58 remains shadow-only; no selection,
truth, policy, readout, flow, packet, or resource authority is added. Existing
fortification queries remain on their frozen schema.

The new rows are outcome-free at choice time. Only the already selected action
may later receive the existing delayed durability label; nonselected choices
remain explicitly censored. Therefore PR59 alone makes no calibration,
counterfactual, ranking, gameplay, score, or win-rate claim.

## Acceptance

Focused feature and calibration compatibility tests cover complete grounding,
stale routes, missing routes, action mismatches, domain rejection, duplicate
projection rejection, outcome absence, and byte-identical frozen-model
predictions. The 20 focused tests pass. The broader alternative-collection,
episode-induction, FDAS-config, and harness suites pass all 180 tests.

A clean one-game engine smoke was the next gate. It had to show that move choice
queries carry the exact PR59 schema, that at least one multi-candidate set has
more than one grounded transition signature when its native mechanics differ,
and that frozen prediction values, action decisions, rejection counts, and
authority flags remain unchanged.

The first clean integration attempt from commit `24ee0b3` reached turn 161
without engine failures or rejected actions, but failed this feature-yield
gate: all 436 move rows reported `route-stale`. Native path queries are issued
earlier in the same authoritative refresh, so their source sequence is
non-future but normally lower than the aggregate snapshot sequence. The first
implementation incorrectly required equality even though the existing bounded
movement authority requires the same turn plus `route.source_seq <=
snapshot.source_seq`, then revalidates actor origin, moves, transport state,
destination, and first step. The correction applies those established
semantics to both PR59 and the latent PR58 grounding check. Tests prove an
earlier same-turn route is accepted and a future route is rejected. The failed
attempt is not feature-yield evidence and will not be pooled with the corrected
smoke.

The corrected clean smoke from commit
`6029496c3f3389e7185a67e29d498146a766b543` passes. Seed `108013` reached
observed turn 161 with zero infrastructure failures, resumes, or rejected
actions. All 435 move rows have complete grounding, with 22 distinct
transition signatures. Seventy-five choice sets offered at least two moves and
65 of them contained at least two distinct signatures. All 19 fortification
rows remained on their frozen schema. The auditor reproduced byte-identical
PR40 predictions for every enriched move row, and the parent PR58 audit still
reports 95 honest abstentions, zero eligible preferences, and zero action
changes. Report
`fdas-pr59-candidate-transition-feature-smoke.json` passes every gate with hash
`b1a37e81fcd2e17be8cf2f040f6a7690aa96f8e0dcda9d79a26d05d592f52726`.

With that mechanics gate closed, a separately preregistered discovery/
confirmation design may fit candidate-specific values. It must reserve games
and lineages
before fitting, evaluate calibration and discrimination on untouched games,
retain interval uncertainty, and abstain outside complete grounded support.
