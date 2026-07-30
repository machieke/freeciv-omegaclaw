# Calibrated transition/readout research status

Status date: 2026-07-29
Branch: `experimental/pln-pressure–bridge–fluid`
Frozen predecessor: `242fd25`
Claim status: no FreeCiv score or win-rate claim

## Executive result

The CT0–CT4 implementation and offline mechanism gates are complete. The
controller now learns authoritative realized goal relief under an exact
category/lifecycle/goal key, abstains when support is incomplete, protects
scalar/terminal/safety candidates from bridge exclusion, supports corrected
probes as membership-only evidence, and can apply bounded path persistence
only after calibrated authority is active.

The offline results are intentionally claim-ineligible:

- raw held-out relief MAE: `0.1291`;
- calibrated held-out relief MAE: `0.0267`;
- MAE improvement: `0.1023`;
- interval coverage: `1.000`;
- exact-support authority rate: `1.000`;
- scalar top-3 recall: `0.250`;
- deterministic protected-bridge recall: `0.850`;
- corrected-probe recall: `0.990`;
- synthetic reversible switch reduction: `1.000`;
- maximum persistence priority regret: `0.0126`.

The first engine-backed collection and frozen-fit gate is also complete:

- collection: `30/30` complete pairs and `60/60` complete arms;
- infrastructure or run failures: `0`;
- authoritative selected-action observations: `1,541`;
- duplicate observations: `0`;
- exact observed keys passing support and interval gates: `9/14`;
- training decisions with complete candidate support: `1,518/1,547`
  (`98.13%`);
- unsupported decisions: `29`, all retained on the frozen scalar fallback.

These results show that the implementations have their intended effects in
the preregistered synthetic regimes and that the frozen model has sufficient
decision-level coverage to enter the CT1 diagnostic. They do not show that
FreeCiv score, gameplay, or win rate improves.

## Stage status

| Stage | Implementation | Offline gate | Engine gate | Authority |
|---|---|---|---|---|
| CT0 frozen scalar PF-v2 + packets | complete | passed | captured replay passed | supported comparator |
| CT1 calibrated scalar | complete | passed | safety/semantic gate passed; score neutral | fail-closed abstention |
| CT2 protected deterministic bridge | complete | passed | recall mechanism/safety passed; score neutral | membership only |
| CT3 corrected probes | complete | passed | stopped: no incremental recall, higher latency | no supported authority |
| CT4 path persistence | complete | passed | paired diagnostic authorized on CT2 comparator | calibrated near-ties only |
| CT5 source–sink flow | existing numerical layer, newly hard-gated | not entered | not entered | closed |

CT5 remains closed because CT4 has not completed a paired engine diagnostic
and remaining error has not been attributed to route allocation.

## Implemented controls

### Transition calibration

- `TransitionValueObservation` requires authoritative relief provenance and
  has no truth-update surface.
- Exact support is keyed by action category, lifecycle state, and goal.
- Residual correction reports mean, variance, a bounded confidence interval,
  model identity, sample count, support source, and abstention reason.
- Authority activates only when every modeled candidate in the decision has
  calibrated exact-key support.
- An unsupported candidate preserves the raw scalar estimate exactly.
- Observation IDs are idempotent; collisions fail without partial mutation.
- Atomic batch fitting persists once, while live single outcomes retain their
  durable update behavior.
- Frozen models require an existing explicit path and identity, are loaded
  read-only, and cannot learn from evaluation outcomes.

### Decision-safe readout

- The protected union contains scalar top-K, the scalar winner, terminal
  candidates, safety candidates, and bridge/probe additions.
- Bridge magnitude and corrected-probe weight can change membership only.
- Final ordering remains scalar/calibrated typed ordering.
- Raw probe count cannot scale current or enter the final score.
- The historical city-founding exclusion case is explicitly protected.

### Path persistence

- Corridors use stable semantic action/actor/city/category/lifecycle identity.
- Smoothing, dwell, hysteresis, diversity, and a maximum priority-regret gate
  are explicit.
- State expires when a route leaves the authoritative candidate set.
- Terminal/irreversible scalar winners reset and bypass persistence.
- Persistence is disabled unless transition calibration has decision
  authority.

### Research sequencing

Five disjoint claim-ineligible engine cohorts are predeclared:

1. `transition_value_collection_diagnostic_v1`;
2. `calibrated_scalar_diagnostic_v1`;
3. `protected_bridge_readout_diagnostic_v1`;
4. `corrected_probe_readout_diagnostic_v1`;
5. `path_persistence_diagnostic_v1`.

The collection cohort writes selected-action outcome pairs. A separate fitter
accepts only completed, clean-source, claim-ineligible traces and produces a
frozen model plus a support report. Evaluation cohorts use that committed
read-only model. Seeds are disjoint across all five stages.

## Evidence and verification

- Offline report:
  `docs/freeciv/evidence/pf-calibrated-transition-readout-offline-v1.json`
- Offline evaluator:
  `scripts/freeciv/run_transition_readout_experiment.py`
- Frozen engine-trained model:
  `docs/freeciv/evidence/pf-transition-value-training-v1-model.json`
- Frozen-fit provenance and exact support report:
  `docs/freeciv/evidence/pf-transition-value-training-v1-report.json`
- Decision-level support coverage:
  `docs/freeciv/evidence/pf-transition-value-training-v1-coverage.json`
- CT1 paired engine diagnostic:
  `docs/freeciv/evidence/pf-calibrated-scalar-diagnostic-v1.json`
- CT2 protected-bridge engine diagnostic:
  `docs/freeciv/evidence/pf-protected-bridge-readout-diagnostic-v1.json`
- CT3 corrected-probe engine diagnostic:
  `docs/freeciv/evidence/pf-corrected-probe-readout-diagnostic-v1.json`
- Frozen-fit tool:
  `scripts/freeciv/fit_transition_value_model.py`
- Schema-valid UI proof trace:
  `Autotests/fixtures/freeciv-events/v1/calibrated-readout.jsonl`
- Browser proof:
  `apps/freeciv-observability/proofshot-artifacts/2026-07-29_22-46-06_verify-calibrated-transition-protected-c/`

Verification completed at this checkpoint:

- 81 focused controller/event/runtime tests passed before evaluator work;
- 8 transition/evaluator tests passed after atomic fitting;
- 91 harness tests passed;
- the complete observability suite passed: 40 tests, fixture validation,
  boundary validation, type checking, and production build;
- ProofShot found zero console errors and zero server errors.

## Next executable gate

Run the seed-disjoint `path_persistence_diagnostic_v1` on the CT2
protected-message comparator. CT3 produced `1,514/1,514` healthy probe
batches, but its union decisions, memberships, bridge additions, fallbacks,
and final readouts were exactly identical to deterministic bridge messages.
It added about `20 ms` of planner latency and produced zero score, win, or
safety delta. Corrected probes therefore stop here and are removed from the
CT4 comparator rather than being silently carried forward.
