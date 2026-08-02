# FDAS PR35 defense choice surface smoke

## Claim boundary

This is a claim-ineligible engineering smoke for the observational defense
choice surface. It establishes live materialization, exact legacy-selection
linkage, selected-only delayed outcomes, and candidate yield. It does not fit
a model and makes no calibration, ranking, policy, gameplay, score, or
win-rate claim.

The run began with source commit `f0f3859`; the worktree contained only
regenerated authority replay reports, so the harness correctly marked the
source as dirty. A clean-source preregistered cohort is required before this
surface may feed discovery.

## Mechanism

The new `fdas-defense-choice-surface/1.0` scope contains exact current legal
operations from two action strata:

- `fdas-shadow:city-garrison-deficit:unit_move`;
- `fdas-shadow:unit-fortification-opportunity:unit_fortify`.

The existing planner remains the selector. FDAS records the exact selected
action when it is in scope, opens a non-authorizing episode after server
acceptance, and observes
`durable-selected-actor-city-defense/32-turn/2.0`. Nonselected actions remain
censored. No promoted rule, contextual conductance, or transition estimate is
read into this surface; all rows explicitly carry
`unmodeled-action-stratum` and zero priority delta.

## Live result

Seed `104743` completed the full 160-turn horizon with 302 engine actions,
zero rejected actions, no infrastructure failure, and 30,159 valid events
with zero errors or warnings.

The durable choice store contains:

- 15 choice sets and 71 exact legal choices;
- 15 exact in-scope selections and 56 explicitly censored alternatives;
- 13 multi-candidate choice sets;
- 63 garrison-move rows and eight fortification rows;
- seven selected actions with a complete immediate-relief episode and
  delayed outcome;
- four positive and three negative 32-turn selected-actor outcomes;
- eight selected actions still censored from calibration because no eligible
  delayed label was completed.

The seven observed negatives/positives include real causes: four selected
actors remained at their target cities; one selected actor left the target;
and two target cities were no longer owned or present at the due turn.

This fixes PR34's data-generating failure. The exact fortification-only slice
had zero multi-candidate live sets across three games. The cross-action
surface produced 13 in one game. It does not yet show that any feature predicts
which action will persist, nor that ranking by such a prediction is safe.

## Evidence

- Choice-store audit report:
  `docs/freeciv/evidence/fdas-pr35-defense-choice-surface-smoke.json`
- Audit report hash:
  `10f2eee2bcadab0412bf78c5b525ffd4058649c5503d5bacd462b14a7e89adb6`
- Choice-store SHA-256:
  `fb6c720adcf5c1bda3182a15b15e85ed9a44a3992b399960bd8799ec489d79dd`
- Choice-store digest:
  `e93198f70a054ac2db16350cbf8ed25ee0f818450b24f359e66b286d81b98ba6`
- Episode-store SHA-256:
  `1836ae339c65b9f6c843052f1db154ba7da16804ba0d083d148aa82b32ec3dc2`
- Outcome-label-store SHA-256:
  `b01778f9ae922d3da9a073540595479388c25c63c2545528a908e3c540340c43`
- Event-ledger SHA-256:
  `adcd9779d8fad3c0d6f0091313f280ed5f14ea772f50eb83e269c1ca57637bc6`

All six candidate-choice audit gates pass: store integrity, outcome-free
queries, explicit alternative censorship, exact selected-row linkage,
selected-only export completeness, and absence of quarantine.

## Next gate

Preregister a fresh clean-source discovery-yield cohort before inspecting its
outcomes. Require complete horizons, valid ledgers, both selected action
strata, mixed-action competition, outcome contrast, and enough independently
identified selected outcomes. Only after that gate passes may the selected
rows enter an action-stratified calibrated transition-value discovery split.
