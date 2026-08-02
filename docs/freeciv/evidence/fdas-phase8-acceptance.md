# FDAS Phase 8 aggregate acceptance report

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Acceptance level: belief projection and observation-pressure planning are
engine shadow-live in dedicated profiles; disabled in the default profile

## Realized wiring

- `BeliefProjector` materializes positive-confidence `BeliefStore` revisions in
  bounded opponent scopes with explicit evidence, context, revision,
  simulation-model, confidence-cap, and selection-policy relations.
- Current-turn decay is mandatory. Projection rejects stale belief revisions;
  it never derives disappearance-as-negative evidence from game snapshots.
- Active conflicts remain uncertain belief atoms. Conflict lineages and
  context quarantines are diagnostic/control atoms and cannot become
  authoritative or operation atoms.
- Value-of-information planning derives decision sensitivity from posterior
  counterfactual action readouts and omits tests that cannot change the bounded
  decision.
- Engine-live observation/simulation operations use atomic CPU plus matching
  observation/simulation packet budgets. Evidence enters the ledger only
  through the existing selected-authoritative-return gate.
- Pressure and scheduling consume truth/readouts but do not call belief
  revision, decay, conflict, or quarantine mutation methods.
- Fresh engine cohorts cover explicit belief decay/rematerialization and a
  one-shot observation-pressure packet decision. The latter records identical
  evidence-store hashes before and after planning and has no authority.

## Exit-criterion disposition

| Criterion | Evidence |
|---|---|
| Uncertain facts never authoritative | namespace/authority transaction constraints plus belief projection tests |
| Pressure cannot revise beliefs | read-only projector and VOI conflict scheduling; belief formulas remain solely in `BeliefStore` |
| No hidden absence inference | projector consumes only explicit belief revisions/evidence and emits no snapshot-derived negatives |
| Observe only for decision-sensitive gaps | posterior outcome readouts must cross an explicit action threshold; the fresh PR18 cohort selected exactly one qualifying operation per arm |
| Quarantine cannot authorize | quarantine is diagnostic-only; no legal binding or operation relation is emitted |
| Activation matrix is accurate | belief projection requires its component; uncertain assessment requires belief+observation at `shadow-live`; authority using uncertainty requires both at `bounded-authority` |

## Verification

The component evidence remains covered by the combined FDAS regression. Fresh
engine evidence is recorded in
[`fdas-pr17-belief-shadow.md`](fdas-pr17-belief-shadow.md) and
[`fdas-pr18-observation-pressure-shadow.md`](fdas-pr18-observation-pressure-shadow.md).
Both PR18 event logs pass full schema validation with zero warnings.

## Non-claims

The checked-in default keeps `projection.beliefs=false` and
`uncertain_assessment_enabled=false`. Dedicated profiles declare the proven
shadow-live subset; they do not claim observation execution, authoritative
return, action authority, engine score improvement, calibration, or win-rate
impact. Promotion requires a legal observation-action binding, commit
revalidation, authoritative return through the evidence gate, and fresh
replay/safety evidence.
