# PF-PLN application to the FreeCiv implementation

Status: core vertical slice implemented on `experimental/pln-pressure`

This map applies the PF-PLN phases to the retained PLN-FreeCiv base. The
existing M0-M7 implementation remains authoritative for rules, truth, state,
legal actions, execution, and evaluation.

| PF-PLN phase | Repository realization | Status | Remaining acceptance work |
|---|---|---|---|
| 0 — executable semantics | Typed atoms, truth views, goals, pressure vectors, reverse rules, deterministic scheduler, proof adapter, capital-defense regression, standalone concentration artifact | Implemented | None |
| 1 — goal regression planner | AND blocker allocation, OR route allocation, deadlines, procedural gating, proof-DAG and grounded-impact adapters; deterministic route beam benchmark measures 99.54% relevant pressure concentration and 75.19% fewer premise expansions; byte-real legal-set replay verifies pressure-off/on selection parity | Implemented with synthetic and captured-snapshot acceptance | Expand the complete-legal-set replay corpus before engine evaluation |
| 2 — provenance and contradiction | Immutable token ledger, token-set union, weighted overlap, conflict severity; live belief fusion moved to evidence-weight space | Implemented core | Materialize live conflict atoms and contextual quarantine operations |
| 3 — observation and simulation pressure | `observe` channel, information gain in operation value, observation-policy provenance | Implemented core | Add exhaustive small-graph VOI parity and simulator-backed FreeCiv observation choices |
| 4 — conductance learning | Grounded credit and no-progress updates are connected to live and deferred action outcomes; attempt-scoped state is atomic and feedback-ID idempotent; untried server-advertised routes use an optimistic 1.0 prior; all three observed same-goal v2 abandonment cases followed exactly four grounded city-founding no-progress outcomes | Engine replay acceptance passed | Replace local-effect-only credit with authoritative downstream goal-relief credit |
| 5 — lifecycle clones | Clone posterior update, variance-matched truth, pressure projection, complexity/cap/merge gates | Implemented core | Persist clone lineage and run hidden-context gameplay benchmarks |
| 6 — induction and analogy | Existing opponent memory and rule proposal infrastructure retained | Partial | Route induction/analogy invocation through `expand` pressure and replay gates |
| 7 — LLM gateway | Existing constrained proposer, verification, quarantine, and token configuration retained | Partial | Make expansion pressure, expected proposal value, and validation cost control call timing |
| 8 — differentiable execution | No automatic-differentiation truth engine added | Not implemented | Add the delimited differentiable subset and compare adjoint with requirement/counterfactual pressure |
| 9 — full multi-goal field | Per-goal pressure, derived weights, double-count prevention, cross-goal harm, hard safety veto, budget allocation; live goal truth is grounded in authoritative threat, defense-deficit, city-count, and legal-candidate state; both fresh 40-pair pressure-only pilots completed with exact isolation and zero failures | V2 stable but outcome-neutral | Add downstream goal-relief semantics and run another fresh pilot; do not freeze confirmatory evidence yet |

## Non-negotiable integration rules

1. Engine state remains ground truth.
2. Pressure never appears in a truth or revision formula.
3. The scheduler does not perform logical inference.
4. Associative or diagnostic support cannot authorize an action.
5. LLM output remains quarantined until verified.
6. Existing snapshot, monitor, legal-action, and execution gates remain in
   force after PF-PLN selection.
7. New empirical claims require a fresh, predeclared paired-seed cohort.

## Next empirical gates

1. Extend conductance feedback from immediate candidate-local effects to
   authoritative downstream goal relief, keeping the truth/pressure firewall.
2. Add offline replay acceptance proving that local success without goal
   progress cannot receive positive teleological credit.
3. Use the v1 paired SD of 3.0875 as a planning input only. A two-point score
   effect requires at least 30 fresh pairs at 80% target power; freeze a
   confirmatory cohort only after the revised pilot shows a positive signal.
4. Predeclare a new seed-disjoint pilot only after the downstream-relief
   implementation and replay gates pass; do not pool it with v1 or v2.
5. Enable live clone splitting only after the per-atom cap and lineage
   forwarding are persisted transactionally.
