# PF-PLN application to the FreeCiv implementation

Status: core vertical slice implemented on `experimental/pln-pressure`

This map applies the PF-PLN phases to the retained PLN-FreeCiv base. The
existing M0-M7 implementation remains authoritative for rules, truth, state,
legal actions, execution, and evaluation.

| PF-PLN phase | Repository realization | Status | Remaining acceptance work |
|---|---|---|---|
| 0 — executable semantics | Typed atoms, truth views, goals, pressure vectors, reverse rules, deterministic scheduler, proof adapter, capital-defense regression, standalone concentration artifact | Implemented | None |
| 1 — goal regression planner | AND blocker allocation, OR route allocation, deadlines, procedural gating, proof-DAG and grounded-impact adapters; deterministic route beam benchmark measures 99.54% relevant pressure concentration and 75.19% fewer premise expansions; byte-real legal-set replay verifies pressure-off/on selection parity | Implemented with synthetic and captured-snapshot acceptance | Expand the complete-legal-set replay corpus before engine evaluation |
| 2 — provenance and contradiction | Immutable token ledger, token-set union, weighted overlap, declared conflict thresholds, explicit conflict atoms, deterministic contextual quarantine operations and views, full deduction ancestry, proof-cycle rejection, causal conflict/quarantine events | Implemented; adversarial Phase 2 acceptance passed with 8,192 duplicate paths, zero overlap errors or false conflicts, and 256/256 cycles rejected | None |
| 3 — observation and simulation pressure | Exact bounded one-step expected information gain, exhaustive outcome enumeration, conflict-driven observation pressure, cost-aware action/observation scheduling, explicit simulator identity and confidence caps, observation-policy provenance, and conservative selection-effect uncertainty widening | Implemented; 256/256 exhaustive rankings matched across 1,024 tests and selected tests beat uniform random by 0.365 bits (184.8% lift) | None |
| 4 — conductance learning | Immediate execution effects and goal relief are separate; goal-neutral effects receive bounded no-progress decay, authoritative direct relief receives monotonic credit, and one pending route per category may receive idempotent downstream credit from a later same-goal change; exact failed actions/sites are suppressed before ranking; a newly grounded, same-goal-best direct city/hut completion receives the initial prior without mutating learned category state; attempt-scoped state remains atomic and truth-free | Deterministic, retrospective, 40-pair pilot, and 100-pair confirmation acceptance passed; confirmation score delta +0.03 [-0.25, 0.31] does not support an improvement claim | Test any further score hypothesis only through a materially different, predeclared gameplay mechanism |
| 5 — lifecycle clones | Clone posterior update, variance-matched truth, expectation and worst-tail pressure projection, predictive/complexity/cap/successor/merge gates, atomic persistent state, idempotent transactions, and transitive lineage forwarding | Implemented; exact hidden-context ablation improves expected planning success from 50% to 82% and mean log likelihood by 0.368 nats | None; live profile enablement remains opt-in |
| 6 — induction and analogy | Bounded contextual pattern mining, quarantined rule/generalization artifacts, relational-profile similarity, structure-checked analogy with transfer uncertainty, `expand` pressure/value/cost gating, independent held-out replay, contradiction-safe promotion/demotion, atomic lifecycle persistence, and strict causal events | Implemented; deterministic held-out replay improves Brier by 0.137 and activated-rule calibration error by 0.687 without increasing contradictions, while the overgeneralized rule is demoted | None |
| 7 — LLM gateway | Typed gap requests, canonical expansion-pressure/usefulness/relief-per-cost admission, hard per-turn and total token reservations, structured proposal envelopes, low initial confidence, explicit validation plans, strict quarantine, typed prompt sanitization, causal events, and an end-to-end no-admission/no-call loop over the existing proposer/verifier/grader | Implemented; fixed 100-case ablation raises validated proposals per token by 63.16%, schedules zero low-pressure calls, and has zero quarantine escapes | None |
| 8 — differentiable execution | Pressure-free strength/confidence tensors, reverse-mode autodiff for smooth product-AND and probabilistic-OR paths, separately typed goal adjoints and learning gradients, bounded monotonic rule-parameter calibration, finite-difference audits, symbolic requirement allocation, intervention/coalitional counterfactuals, and explicit threshold exclusion | Implemented; 1,444 active smooth comparisons match finite differences within 4.97e-11, while dead-AND and threshold cases demonstrate the required non-gradient operators | None |
| 9 — full multi-goal field | Per-goal pressure, derived weights, double-count prevention, cross-goal harm, lexicographic actionable-safety firewall, budget allocation; survival requires a grounded production coverage deficit or a visible opponent within configured wrapped distance of an owned city/unit anchor; a fortification opportunity alone does not create a deficit; grounded Impact operations receive category-level pressure so legal alternative count cannot dilute a goal; cross-goal grounded utility loss is scheduled once as a goal-shared opportunity cost; category routing assigns defense production to survival and population recovery to score; eight fresh 40-pair pressure pilots completed with exact isolation | Direct-completion confirmation passed semantic, safety, source, schema, and exact-replay gates, but its +0.03 score delta [-0.25, 0.31] did not confirm a material score improvement; lead/win rate was not declared | Do not repeat or pool the pressure-only hypothesis; predeclare a materially different gameplay mechanism before further score testing |

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

The frozen `pressure_direct_completion_confirmatory_v1` gate is complete. All
100 disjoint pairs passed clean-source, initial-state, policy-isolation,
safety, schema, provenance, and exact-replay acceptance. The standalone
predeclared endpoint was +0.03 points with interval [-0.25, 0.31] and did not
support the +0.5-point score claim. Lead/win rate was not declared, and the
pilot and confirmation are not pooled.

1. Define a materially different gameplay mechanism and its causal,
   decision-level diagnostic before opening another score cohort.
2. Freeze its minimum relevant effect, cohort size, disjoint seed namespace,
   safety gates, and claim endpoint before execution.
3. Retain pressure-only direct-completion behavior as semantically accepted,
   but do not describe it as score-improving.
4. Keep live clone splitting opt-in through the now-persistent lifecycle store;
   do not bypass its per-atom cap, predictive-gain, complexity, lineage, or
   merge gates.
