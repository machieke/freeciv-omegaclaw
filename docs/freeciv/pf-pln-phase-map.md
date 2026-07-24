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
| 4 — conductance learning | Immediate execution effects and goal relief are separate; goal-neutral effects receive bounded no-progress decay, authoritative direct relief receives monotonic credit, and one pending route per category may receive idempotent downstream credit from a later same-goal change; exact failed actions/sites are suppressed before ranking; a newly grounded, same-goal-best direct city/hut completion receives the initial prior without mutating learned category state; attempt-scoped state remains atomic and truth-free | Deterministic, retrospective, and fresh 40-pair direct-completion engine/replay acceptance passed; pilot score delta +0.475 [0.075, 0.975] remains claim-ineligible | Complete the fresh score-only confirmatory cohort |
| 5 — lifecycle clones | Clone posterior update, variance-matched truth, pressure projection, complexity/cap/merge gates | Implemented core | Persist clone lineage and run hidden-context gameplay benchmarks |
| 6 — induction and analogy | Existing opponent memory and rule proposal infrastructure retained | Partial | Route induction/analogy invocation through `expand` pressure and replay gates |
| 7 — LLM gateway | Existing constrained proposer, verification, quarantine, and token configuration retained | Partial | Make expansion pressure, expected proposal value, and validation cost control call timing |
| 8 — differentiable execution | No automatic-differentiation truth engine added | Not implemented | Add the delimited differentiable subset and compare adjoint with requirement/counterfactual pressure |
| 9 — full multi-goal field | Per-goal pressure, derived weights, double-count prevention, cross-goal harm, lexicographic actionable-safety firewall, budget allocation; survival requires a grounded production coverage deficit or a visible opponent within configured wrapped distance of an owned city/unit anchor; a fortification opportunity alone does not create a deficit; grounded Impact operations receive category-level pressure so legal alternative count cannot dilute a goal; cross-goal grounded utility loss is scheduled once as a goal-shared opportunity cost; category routing assigns defense production to survival and population recovery to score; eight fresh 40-pair pressure pilots completed with exact isolation | Direct-completion pilot passed all semantic gates and produced the first positive score interval, but remains claim-ineligible; lead-rate evidence remains insufficient | Run the predeclared 100-pair score-only confirmation without pooling |

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

1. Commit the frozen `pressure_direct_completion_confirmatory_v1` score design.
2. Run all 100 disjoint paired seeds without pair limiting and require clean
   source, initial-state, policy-isolation, safety, schema, provenance, and
   exact-replay acceptance.
3. Evaluate the predeclared 0.5-point score endpoint without pooling any pilot.
4. Treat lead/win rate as descriptive only; the confirmatory cohort is not
   powered for the pilot's sparse discordance rate.
5. Enable live clone splitting only after the per-atom cap and lineage
   forwarding are persisted transactionally.
