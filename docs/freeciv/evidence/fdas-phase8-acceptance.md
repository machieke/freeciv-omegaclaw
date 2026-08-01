# FDAS Phase 8 aggregate acceptance report

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Acceptance level: component-only / shadow-capable; disabled in the default profile

## Realized wiring

- `BeliefProjector` materializes positive-confidence `BeliefStore` revisions in
  bounded opponent scopes with explicit evidence, context, revision,
  simulation-model, confidence-cap, and selection-policy relations.
- Current-turn decay is mandatory. Projection rejects stale belief revisions;
  it never derives disappearance-as-negative evidence from game snapshots.
- Active conflicts remain uncertain belief atoms. Conflict lineages and
  context quarantines are diagnostic/control atoms and cannot become
  authoritative or operation atoms.
- Value-of-information planning omits tests that cannot change a declared
  bounded decision.
- Engine-live observation/simulation operations use atomic CPU plus matching
  observation/simulation packet budgets. Evidence enters the ledger only
  through the existing selected-authoritative-return gate.
- Pressure and scheduling consume truth/readouts but do not call belief
  revision, decay, conflict, or quarantine mutation methods.

## Exit-criterion disposition

| Criterion | Component evidence |
|---|---|
| Uncertain facts never authoritative | namespace/authority transaction constraints plus belief projection tests |
| Pressure cannot revise beliefs | read-only projector and VOI conflict scheduling; belief formulas remain solely in `BeliefStore` |
| No hidden absence inference | projector consumes only explicit belief revisions/evidence and emits no snapshot-derived negatives |
| Observe only for decision-sensitive gaps | hard VOI eligibility gate; zero sensitivity/gain/feasibility/success/deadline fit is omitted |
| Quarantine cannot authorize | quarantine is diagnostic-only; no legal binding or operation relation is emitted |
| Activation matrix is accurate | belief projection requires its component; uncertain assessment requires belief+observation at `shadow-live`; authority using uncertainty requires both at `bounded-authority` |

## Verification

The combined FDAS, belief, observation, pressure, packet, resource, and domain
lifecycle and activation regression passed `357` tests. Focused configuration
tests cover the new component, shadow-live, and bounded-authority thresholds.

## Non-claims

The checked-in default keeps `projection.beliefs=false` and
`uncertain_assessment_enabled=false`. The manifest declares only
`component-only`; it does not claim live shadow integration, action authority,
engine score improvement, calibration, or win-rate impact. Promotion requires
fresh runtime wiring and replay/safety evidence, followed by an explicit
capability-status change.
