# FDAS Phase 9 aggregate acceptance report

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Acceptance level: component-only; learning and policy readout disabled by default

## Realized wiring

- The durable compact `DecisionEpisodeStore` persists immutable causal
  identity and supports restart-safe resolution by operation ID.
- Defense attribution distinguishes acceptance, pending delay, immediate
  effect, effect without goal relief, authoritative goal relief, closed
  no-effect, and confounded/unattributable outcomes.
- `FdasEpisodeLearningAdapter` accepts only attributable terminal outcomes and
  writes episode-linked `ControlCalibrationRecord` values to an append-only
  calibration ledger and exact-context conductance store.
- Duplicate episode replay is idempotent. Confounded, contradicted, unresolved,
  unlinked, and pending outcomes abstain.
- `FdasEpisodeInductionAdapter` converts only attributable terminal episodes.
  Context features are explicitly declared; additional features must cite
  evidence already linked by the episode. Shared execution lineage cannot
  inflate independent support.
- The existing bounded induction engine mines immutable proposals into
  quarantine. Disjoint held-out replay controls promotion; structural
  promotion additionally requires committed validation packets.
- Read-only metrics expose outcome counts, attributable/confounded totals,
  sample and route-context counts, relief MAE, success Brier score, and a
  deterministic conductance hash. Per-episode explanations expose prediction,
  calibration, conductance, eligibility, and abstention reason.
- The FDAS configuration now has independent attribution, contextual
  conductance, conductance-authority, induction, and induced-rule-readout
  flags. Every flag defaults to false.

## Exit-criterion disposition

| Criterion | Component evidence |
|---|---|
| Duplicate replay is idempotent | immutable episode identity plus calibration/conductance duplicate tests |
| Acceptance, effect, and relief are distinct | terminal state model and delayed defense observation tests |
| Route conductance is truth-free | typed control-only calibration target; adapter reports `truth_mutated=false` and has no AtomSpace transaction |
| Context estimates are gated | contextual estimator tests cover sample count, uncertainty width, context/ruleset/policy identity, calibration, disjoint holdout, and supported-context regression |
| Induced rules have zero quarantine escape | ledger exposes only held-out-promoted rules; structural promotion requires validation and committed packets |
| Authority is opt-in and versioned | all learning flags default false; shadow and authority flags require exact manifest capabilities at `shadow-live` or `bounded-authority` |

## Verification

The aggregate FDAS, belief, observation, pressure, packet, calibration,
contextual transition, induction, operation, resource, movement, transport,
combat, configuration, and structural-operation regression passed `410`
tests.

## Non-claims

The checked-in manifest declares all Phase 9 capabilities only
`component-only`; it does not claim shadow-live use, calibrated authority,
engine-live behavior, replay impact, score improvement, or win-rate impact.
The default profile disables episode learning, conductance authority,
induction, and induced-rule readout. Promotion requires a frozen model,
disjoint held-out evidence, live replay/safety validation, and an explicit
manifest status change. No legacy action path is removed by this phase.
