# FDAS PR82 bounded replacement-execution pilot

Date: 2026-08-04

## Result

PR82 passes all eleven corrected audit gates from clean implementation commit
`fc431b839fe4e5b43a09231cab935008c7b04efd`. The deliberately reused seed
`109459` completed the 160-turn horizon without resume or infrastructure
failure. All 315 engine actions were accepted and the valid event ledger
contains 61,575 events.

The forced treatment assigned exactly one grounded coordinated-replacement
operation at turn 33. The durable assignment retained the same operation and
specification identity throughout six exact action attempts:

- replacement actor `122` moved for three accepted steps on turns 33–35;
- reinforcement actor `108` moved for three accepted steps on turns 35–37;
- every temporary route or move-point loss abstained until a current native
  route and byte-identical legal action returned;
- four of the six authorizations changed the legacy-selected action, while two
  selected the action the legacy planner already preferred; and
- authoritative placement predicates advanced the first step on turn 35 and
  completed the full chain on turn 37.

Completion opened exactly one PR81 label with due turn 69. The first eligible
assessment occurred on turn 74 and observed a negative 32-turn durability
outcome: both cities remained owned and present, but neither assigned actor was
still present, so neither required placement conjunct held. This is a real
completion-indexed negative observation, not an action rejection or inferred
first-step effect.

The deterministic report is
`fdas-pr82-bounded-replacement-execution-pilot.json`, structural hash
`d5e51d12f87d5ab6ee656977dc80e7ea2df96bccb16781b075beb15b3264d3ea`.
A second invocation produced byte-identical JSON with SHA-256
`671835cd69b789021880a7392914d40ab59b7c2b1b93f2224a8c4228d7d48aed`.

## Audit correction

The first audit invocation returned false on two composition errors, not on a
treatment failure. The inherited lifecycle audit counted explicitly prefixed
`execution-*` transitions as ordinary adapter reconciliation passes, and the
new audit expected a rejection counter in a terminal summary that exposes
only the action total. The correction is specified in
`fdas-pr82-audit-composition-correction.md`, has a mixed-stream regression,
and was applied to the same immutable run. It does not change the seed,
horizon, assignment, actions, stores, outcome, or source identity.

## Mechanical interpretation

The run establishes the missing multi-snapshot execution mechanism. One
grounded chain can be selected once, durably owned, reserved, activated,
temporarily blocked, exactly reactivated, rematerialized through the ordinary
planner, accepted by the final execution gate, advanced only from subsequent
authoritative state, completed, and linked to a delayed outcome. Restart,
tamper, stale-binding, and terminal no-reassignment boundaries are covered by
the focused suite; 99 focused tests and all 115 shared harness tests pass.

The negative outcome is scientifically important but not an estimate. The six
steps are repeated measurements inside one assigned game and are not six
independent samples. This known seed was selected for opportunity, treatment
was forced after opportunity appeared, and there is no simultaneous control.
The result therefore cannot estimate treatment effect or justify changing the
default policy.

## Next boundary

The next experiment must assign treatment at the game/seed cluster before
gameplay and compare it with a frozen control behavior on fresh seeds. It must
predeclare opportunity missingness, cluster-level outcomes, a minimum number
of contributing games in both arms, stopping, attrition handling, confidence
intervals, and the rule for pending labels at horizon. Calibration fitting and
policy promotion remain prohibited until independent completion-indexed
outcomes show both usable yield and value.

The turn-74 negative label also motivates read-only cause attribution for
assigned-actor disappearance. That diagnostic may distinguish destruction,
upgrade, transport, disband, or unexplained removal, but it must not relabel
the frozen durability outcome.

## Claim boundary

PR82 establishes one known-seed, claim-ineligible coordinated-replacement
execution and completion-indexed outcome chain. It does not establish causal
benefit, calibrated transition value, policy improvement, score impact, or win
rate. Its single observed outcome is negative and cannot be generalized.
