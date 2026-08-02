# FDAS Phase 8 aggregate acceptance report

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Acceptance level: belief projection, observation-pressure planning,
legacy-bound visibility return, and independent-lineage conflict/quarantine
are engine shadow-live in dedicated profiles; disabled in the default profile

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
- A separate visibility-frontier profile binds a selected test only to the
  byte-identical move already selected by legacy, exact-revalidates the move,
  and accepts evidence only from a fresh authoritative visibility delta.
  Accepted moves without a provable endpoint actor are explicitly censored and
  write no evidence.
- A claim-ineligible contradiction profile places one capped, non-exact model
  prior before reading a public player-roster packet. The independent visible
  lineage revises the same proposition, creates an explicit conflict, directly
  causes every context quarantine, and rematerializes the diagnostic graph
  without action authority.

## Exit-criterion disposition

| Criterion | Evidence |
|---|---|
| Uncertain facts never authoritative | namespace/authority transaction constraints plus belief projection tests |
| Pressure cannot revise beliefs | read-only projector and VOI conflict scheduling; belief formulas remain solely in `BeliefStore` |
| No hidden absence inference | projector consumes only explicit belief revisions/evidence and emits no snapshot-derived negatives |
| Observe only for decision-sensitive gaps | posterior outcome readouts must cross an explicit action threshold; the fresh PR18 cohort selected exactly one qualifying operation per arm |
| Quarantine cannot authorize | the PR21 engine cohort projected two conflicts and four complete context quarantines while emitting no legal binding, operation authority, or FDAS authority action |
| Activation matrix is accurate | belief projection requires its component; uncertain assessment requires belief+observation at `shadow-live`; authority using uncertainty requires both at `bounded-authority` |
| Return cannot fabricate evidence | 72 exact bindings produced 70 authoritative evidence returns and two causally complete no-write abstentions in the PR20 cohort |

## Verification

The component evidence remains covered by the combined FDAS regression. Fresh
engine evidence is recorded in
[`fdas-pr17-belief-shadow.md`](fdas-pr17-belief-shadow.md) and
[`fdas-pr18-observation-pressure-shadow.md`](fdas-pr18-observation-pressure-shadow.md).
The execution continuation is recorded in
[`fdas-pr20-observation-return.md`](fdas-pr20-observation-return.md), and the
contradiction continuation in
[`fdas-pr21-belief-conflict.md`](fdas-pr21-belief-conflict.md). Both PR18,
both PR20, and both PR21 event logs pass full schema validation with zero
warnings.

## Non-claims

The checked-in default keeps `projection.beliefs=false` and
`uncertain_assessment_enabled=false`. Dedicated profiles declare the proven
shadow-live subset; they do not claim authoritative return for opponent
presence, FDAS action choice, engine score improvement, calibration, or
win-rate impact. PR20 proves only a visibility-frontier return bound to a
legacy-selected move. PR21 uses an intentionally false diagnostic prior and
therefore proves conflict/quarantine mechanics, not model quality. Any
FDAS-selected observation action or authority using uncertain beliefs requires
separate evidence and activation.
