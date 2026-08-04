# FDAS PR84 intention-outcome component foundation

Date: 2026-08-04

## Implemented boundary

The PR84 paired design now has a typed, authority-free component substrate:

- one atomic, identity-bound assignment per game;
- arm fixed to `control` or `treatment` by construction;
- deterministic binding to the first grounded coordinated-replacement pair;
- immutable actor, city, operation, specification, assignment-turn, snapshot,
  and due-turn identity;
- restart-safe pending, observed, and censored state;
- the same assignment-turn-plus-32 observation window in both arms;
- authoritative source/target city retention;
- ruleset-grounded persistent-defender counts at both city tiles;
- exact assigned-actor presence, placement, and transport components; and
- the current durable operation state as a mechanism field.

The tracker does not activate, reserve, select, rematerialize, or execute an
action. Treatment authority remains exclusively in the separately gated PR82
executor; control cannot gain authority through this component.

## Verification

Component tests exercise first-opportunity binding, logical-pair identity,
control-arm semantics, the 32-turn due boundary, observation, all three bounded
count summaries, atomic restart, digest verification, and persistence-identity
quarantine. Sixteen replacement lifecycle tests pass, and static analysis and
compilation are clean.

## Open work

The engine harness still needs separate control/treatment manifests, durable
event/counter integration, horizon censoring, exact treatment-assignment
cross-checking, a pair runner with deterministic arm order, and the frozen
paired audit/analysis. No fresh PR84 seed has been executed.

## Claim boundary

This checkpoint establishes component mechanics only. It supplies no live
outcome, treatment comparison, transition value, policy, score, or win-rate
evidence.
