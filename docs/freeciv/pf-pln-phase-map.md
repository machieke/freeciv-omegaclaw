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
| 4 — conductance learning | Immediate execution effects and goal relief are separate; goal-neutral effects receive bounded no-progress decay, authoritative direct relief receives monotonic credit, and one pending route per category may receive idempotent downstream credit from a later same-goal change; attempt-scoped state remains atomic and truth-free; v1 direct callers and events remain compatible | Offline acceptance and four fresh 40-pair engine/replay gates passed; outcome neutral | Keep learning frozen while cross-goal scheduling semantics are corrected |
| 5 — lifecycle clones | Clone posterior update, variance-matched truth, pressure projection, complexity/cap/merge gates | Implemented core | Persist clone lineage and run hidden-context gameplay benchmarks |
| 6 — induction and analogy | Existing opponent memory and rule proposal infrastructure retained | Partial | Route induction/analogy invocation through `expand` pressure and replay gates |
| 7 — LLM gateway | Existing constrained proposer, verification, quarantine, and token configuration retained | Partial | Make expansion pressure, expected proposal value, and validation cost control call timing |
| 8 — differentiable execution | No automatic-differentiation truth engine added | Not implemented | Add the delimited differentiable subset and compare adjoint with requirement/counterfactual pressure |
| 9 — full multi-goal field | Per-goal pressure, derived weights, double-count prevention, cross-goal harm, lexicographic actionable-safety firewall, budget allocation; survival requires a grounded production coverage deficit or a visible opponent within configured wrapped distance of an owned city/unit anchor; a fortification opportunity alone does not create a deficit; grounded Impact operations receive category-level pressure so legal alternative count cannot dilute a goal; cross-goal grounded utility loss is scheduled once as a goal-shared opportunity cost; category routing assigns defense production to survival and population recovery to score; six fresh 40-pair pressure pilots completed with exact isolation | Opportunity-cost deterministic and retrospective replay acceptance passed; fresh engine evaluation pending | Run the predeclared opportunity-cost smoke/pilot; do not freeze confirmatory evidence |

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

1. Run the one-pair prefix of predeclared
   `pressure_opportunity_cost_pilot_v1` and require finite schema-valid
   rejected scores, correct safety admissibility, and zero exact-replay
   failures.
2. Continue the remaining seed-disjoint pairs only if engine, schema, source,
   safety, candidate-isolation, and replay smoke gates pass.
3. Report safe city-founding and known-hut displacement, safety selection,
   settlement outcomes, and paired score without tuning goal weights.
4. Do not pool the category-invariance estimate (-0.225, interval
   [-0.800, 0.325]) with earlier pilots and do not freeze confirmatory
   evidence without a positive fresh signal.
5. Enable live clone splitting only after the per-atom cap and lineage
   forwarding are persisted transactionally.
