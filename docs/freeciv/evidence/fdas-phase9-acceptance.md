# FDAS Phase 9 aggregate acceptance report

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Acceptance level: episode attribution, contextual conductance, and
quarantine-only induction `shadow-live` in dedicated profiles; held-out
promotion/readout `component-only` and disabled by default

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
  promotion additionally requires committed validation packets. A promoted
  replay verdict now also requires a versioned approval record bound to exact
  training/holdout artifacts and episode partitions; approval grants neither
  policy nor readout authority.
- A component-level held-out gate rejects shared store identity, artifact
  digest, episode IDs, or causal provenance, persists promotion/demotion
  verdicts, and is idempotent under repeat evaluation.
- A dedicated engine-live shadow bridge now encodes durable defense episodes,
  evaluates the bounded miner, persists even an empty hash-bound ledger, and
  fails closed if any promoted rule appears. It has no truth or policy
  authority and no rule readout.
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
| Induced rules have zero quarantine escape | component lifecycle tests require a versioned artifact-bound approval for every promotion; a clean 160-turn engine run retained a durable hash-valid ledger with zero validation/readout events and zero promoted rules |
| Authority is opt-in and versioned | all learning flags default false; shadow and authority flags require exact manifest capabilities at `shadow-live` or `bounded-authority` |

## Verification

The original aggregate component regression passed `410` tests. The live
induction increment additionally passes 99 focused configuration, runtime,
episode, learning, induction, and evidence-audit tests; its durability
correction passed the 18 focused induction/audit tests. The later approval and
held-out gate hardening adds focused promotion, demotion, overlap, persistence,
and replay-idempotence coverage; fresh aggregate counts should be recorded
with the next engine-backed induction cohort.

## Non-claims

The checked default manifest remains `component-only`. Dedicated manifests now
declare live episode attribution, truth-free contextual conductance, and the
quarantine-only induction bridge at `shadow-live`; they do not declare
held-out promotion or induced-rule readout live. The default profile disables
episode learning, conductance authority, induction, and induced-rule readout.
The accepted run produced five uniformly positive episodes and therefore no
candidate rule; it makes no discovery-quality, calibrated-authority, replay
impact, score-improvement, or win-rate claim. Promotion still requires a
frozen model, disjoint held-out evidence, live replay/safety validation, and
an explicit manifest status change. No legacy action path is removed.
