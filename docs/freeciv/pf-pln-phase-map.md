# PF-PLN application to the FreeCiv implementation

Status: canonical phases 0-9 implemented and acceptance gates recorded on
`experimental/pln-pressure`

This map applies the PF-PLN phases to the retained PLN-FreeCiv base. The
existing M0-M7 implementation remains authoritative for rules, truth, state,
legal actions, execution, and evaluation.

Implementation acceptance does not imply live activation. The checked
[runtime activation matrix](pf-pln-runtime.md) currently enables phases 0, 1,
4, and 9 for a pressure-enabled engine-live scheduler; all other phases are
component-only.

| PF-PLN phase | Repository realization | Status | Remaining acceptance work |
|---|---|---|---|
| 0 — executable semantics | Typed atoms, truth views, goals, pressure vectors, reverse rules, deterministic scheduler, proof adapter, and a standalone capital-defense replay with reproducible pressure and scheduling | Implemented; standalone end-to-end benchmark and truth-firewall acceptance passed | None |
| 1 — goal regression planner | AND blocker allocation, OR route allocation, deadlines, procedural gating, proof-DAG and grounded-impact adapters; deterministic 256-decoy route benchmark measures 99.54% relevant pressure concentration and 8.03x fewer instantiations at equal decision quality; byte-real legal-set and later engine decision replays verify pressure selection | Implemented; canonical >=5x focus gate, captured-snapshot parity, and exact engine replay acceptance passed | None |
| 2 — provenance and contradiction | Immutable token ledger, token-set union, weighted overlap, declared conflict thresholds, explicit conflict atoms, deterministic contextual quarantine operations and views, full deduction ancestry, proof-cycle rejection, causal conflict/quarantine events | Implemented; adversarial Phase 2 acceptance passed with 8,192 duplicate paths, zero overlap errors or false conflicts, and 256/256 cycles rejected | None |
| 3 — observation and simulation pressure | Exact bounded one-step expected information gain, exhaustive outcome enumeration, conflict-driven observation pressure, cost-aware action/observation scheduling, explicit simulator identity and confidence caps, observation-policy provenance, and conservative selection-effect uncertainty widening | Implemented; 256/256 exhaustive rankings matched across 1,024 tests and selected tests beat uniform random by 0.365 bits (184.8% lift) | None |
| 4 — conductance learning | Immediate execution effects and goal relief are separate; goal-neutral effects receive bounded no-progress decay, authoritative direct relief receives monotonic credit, and one pending route per category may receive idempotent downstream credit from a later same-goal change; exact failed actions/sites are suppressed before ranking; a newly grounded, same-goal-best direct city/hut completion receives the initial prior without mutating learned category state; attempt-scoped state remains atomic and truth-free | Implemented; a standalone fixed-prior ablation abandons the infeasible branch after five grounded no-progress attempts versus no abandonment in 12 fixed-prior attempts; direct-completion confirmation remained score-null, while separate expansion confirmations support +2.66 for target three-to-four and +1.56 for target four-to-five through additional settlements and citizen score | None |
| 5 — lifecycle clones | Clone posterior update, variance-matched truth, expectation and worst-tail pressure projection, predictive/complexity/cap/successor/merge gates, atomic persistent state, idempotent transactions, and transitive lineage forwarding; live profile enablement remains opt-in | Implemented; exact hidden-context ablation improves expected planning success from 50% to 82% and mean log likelihood by 0.368 nats | None |
| 6 — induction and analogy | Bounded contextual pattern mining, quarantined rule/generalization artifacts, relational-profile similarity, structure-checked analogy with transfer uncertainty, `expand` pressure/value/cost gating, independent held-out replay, contradiction-safe promotion/demotion, atomic lifecycle persistence, and strict causal events | Implemented; deterministic held-out replay improves Brier by 0.137 and activated-rule calibration error by 0.687 without increasing contradictions, while the overgeneralized rule is demoted | None |
| 7 — LLM gateway | Typed gap requests, canonical expansion-pressure/usefulness/relief-per-cost admission, hard per-turn and total token reservations, structured proposal envelopes, low initial confidence, explicit validation plans, strict quarantine, typed prompt sanitization, causal events, and an end-to-end no-admission/no-call loop over the existing proposer/verifier/grader | Implemented; fixed 100-case ablation raises validated proposals per token by 63.16%, schedules zero low-pressure calls, and has zero quarantine escapes | None |
| 8 — differentiable execution | Pressure-free strength/confidence tensors, reverse-mode autodiff for smooth product-AND and probabilistic-OR paths, separately typed goal adjoints and learning gradients, bounded monotonic rule-parameter calibration, finite-difference audits, symbolic requirement allocation, intervention/coalitional counterfactuals, and explicit threshold exclusion | Implemented; 1,444 active smooth comparisons match finite differences within 4.97e-11, while dead-AND and threshold cases demonstrate the required non-gradient operators | None |
| 9 — full multi-goal field | Per-goal pressure, derived weights, double-count prevention, cross-goal harm, lexicographic actionable-safety firewall, budget allocation; survival requires a grounded production coverage deficit or a visible opponent within configured wrapped distance of an owned city/unit anchor; a fortification opportunity alone does not create a deficit; grounded Impact operations receive category-level pressure so legal alternative count cannot dilute a goal; cross-goal grounded utility loss is scheduled once as a goal-shared opportunity cost; category routing assigns defense production to survival and population recovery to score | Implemented; multi-goal scheduling beats isolated per-goal recommendations in 64/64 conflicting scenarios with both goal explanations preserved; all expansion-target confirmation safety and exact-replay gates pass, with zero safety-selection violations across 473 active decisions | None |

## Non-negotiable integration rules

1. Engine state remains ground truth.
2. Pressure never appears in a truth or revision formula.
3. The scheduler does not perform logical inference.
4. Associative or diagnostic support cannot authorize an action.
5. LLM output remains quarantined until verified.
6. Existing snapshot, monitor, legal-action, and execution gates remain in
   force after PF-PLN selection.
7. New empirical claims require a fresh, predeclared paired-seed cohort.

## Empirical status and next gates

The pressure-only direct-completion confirmation remained null. The materially
different `expansion_target_confirmatory_v1` mechanism then completed all 100
fresh pairs and supported a +2.66 turn-60 own-score effect with interval
[+2.00, +3.32] and exact p=9.214e-12. It passed clean-source,
initial-state, policy-isolation, safety, schema, provenance, and exact-replay
acceptance. The pilot and confirmation are not pooled.

The separately developed `expansion_fifth_city_confirmatory_v1` cohort then
completed 100 new pairs and supported an incremental fourth-to-fifth-city
effect of +1.56, interval [+0.88, +2.23], exact p=1.998e-5. It added 0.53
retained cities and 1.60 citizen-score points. Its diagnostic, pilot, and
confirmation are separate from one another and from the earlier
three-to-four-city cohorts.

1. Treat the +2.66 result as scoped to the frozen
   `civ2civ3`/experimental-AI/turn-60 profile.
2. Require another predeclared, seed-disjoint paired cohort before claiming
   transfer to a different ruleset, opponent, horizon, or expansion target.
3. Do not describe the result as a win-rate gain or as strictly greater than
   two points; neither claim passed its complete gate.
4. Retain pressure-only direct-completion behavior as semantically accepted,
   but do not describe that isolated mechanism as score-improving.
5. Keep live clone splitting opt-in through the now-persistent lifecycle store;
   do not bypass its per-atom cap, predictive-gain, complexity, lineage, or
   merge gates.
6. Treat the +1.56 result as an incremental four-to-five-city turn-60 claim;
   do not add it to +2.66 or describe it as a direct three-to-five-city effect.
