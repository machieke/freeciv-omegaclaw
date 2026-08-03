# PR48 membership-only path-persistence engineering result

## Decision

PR48 implements and validates the cheap path-persistence comparator without
fluid transport. Smoothed corridor reachability, bounded momentum, dwell, and
hysteresis may retain at most one current legal candidate in the protected
union. They cannot alter scalar score, scalar ordering, action selection,
truth, policy/readout authority, advection, capacity allocation, or
source--sink flow.

The implementation is ready for a preregistered fresh shadow cohort. This
engineering result is claim-ineligible and does not establish gameplay or
score improvement.

## Controller boundary

The path identity is stable over action type, actor, city target, lifecycle
turn-phase band, ruleset digest, and map topology. A route must remain on the
exact current candidate surface; absent routes expire immediately. The frozen
controller uses:

| Parameter | Value |
|---|---:|
| smoothing | 0.35 |
| route momentum | 0.15 |
| minimum dwell | 2 decisions |
| dwell bonus | 0.05 |
| switch margin | 0.01 |
| maximum instantaneous reachability regret | 0.05 |

When temporal retention would exceed the regret bound, the controller
reanchors to the current best probe region. Persistence contributes protected
membership only; the frozen scalar rank remains final.

## Clean engine smoke

The clean smoke used source commit
`ac150b8ee1767da66e557e9e4701da5397e1b971`, seed `105071`, the
`civ2civ3` engine, the defense-choice FDAS profile, the dedicated
path-persistence manifest, and a 160-turn horizon. It reached turn 160 in
120.6 seconds with zero rejected actions.

| Measure | Result |
|---|---:|
| persistence-union evaluations | 84 |
| persistence readouts | 164 |
| protected-union members | 128 |
| additions beyond corrected probes | 11 |
| smoothing-retained decisions | 18 |
| dwell-retained decisions | 0 |
| hysteresis-retained decisions | 0 |
| regret-gate reanchors | 12 |
| expired routes | 9 |
| fallbacks | 0 |
| action-selection changes | 0 |

All 11 additions were temporally retained, current-surface candidates; each
had observed reachability regret below `0.05`. The 12 proposals above the
bound were rejected and reanchored. Every event reproduced its result and
signal-ledger hash, exact probe-parent hash and membership, scalar order,
snapshot/revision binding, and controller state continuity. The event ledger
validated without errors or warnings.

The first startup attempt lacked `FREECIV_RULESET_ROOT`. The second used the
base FDAS runtime profile, which correctly rejected a manifest requiring
episode attribution. Both produced zero completed games and are excluded.

## Audit and tests

`scripts/freeciv/audit_fdas_path_persistence_union.py` independently checks:

- clean frozen source, profile, manifest, seed, and accepted endpoint;
- event schema and per-game counter agreement;
- semantic and signal-ledger hashes;
- exact corrected-probe parent binding;
- scalar ordering and winner protection;
- at-most-one protected membership addition;
- state-before/state-after continuity and route expiry;
- distinct smoothing, dwell, hysteresis, and regret attribution;
- the reachability-regret bound and fallback behavior; and
- zero truth, selection, policy/readout, fluid, or score authority leakage.

The smoke passes the auditor under one-game engineering thresholds. Forty-three
focused candidate-union, auditor, and runtime tests pass.

## Historical control result

This comparator does not revive the older CT4 ranking-authority controller.
That controller's preregistered 30-pair pilot produced a paired score delta of
`-0.167` and `+0.50` no-effect actions. PR48 deliberately isolates temporal
signals to candidate membership so those signals cannot reproduce the adverse
ranking intervention.

## Claim boundary and next gate

The engineering smoke shows that bounded temporal retention, expiry, and the
regret safety gate execute coherently in one real engine game. Seed `105071`
and all earlier discovery/confirmation seeds are excluded from confirmation.

The next gate is a fresh preregistered eight-game shadow cohort. Passing may
establish recurrent bounded temporal candidate recall beyond corrected probes.
It cannot establish candidate precision, ranking quality, changed gameplay,
score improvement, or win rate.
