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

## Live paired outcome

The formerly open engine work is complete. Separate arm-locked manifests,
durable events and counters, horizon censoring, exact treatment-assignment
cross-checking, deterministic within-pair order, consequence attribution, and
the frozen paired audit are live. The 32-arm PR84 cohort is mechanically
rejected: 4 no-opportunity pairs, 10 opportunity mismatches, 1 outcome
mismatch, and only 1 matched-observed pair. Six treatment arms preserve
controller infrastructure failures; no arm was retried.

See `fdas-pr84-intention-indexed-paired-replacement.md` and the canonical JSON
report for the complete result. The corrected PR85 cohort is separately
preregistered and cannot be pooled with PR84.

## Claim boundary

The component and its live outcome machinery are proven, but the paired cohort
fails mechanical acceptance and minimum yield. It supplies no treatment-value,
transition-value, policy, score, or win-rate evidence.
