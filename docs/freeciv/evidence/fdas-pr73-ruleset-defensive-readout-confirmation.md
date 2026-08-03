# FDAS PR73 ruleset-defensive readout confirmation

Date: 2026-08-03
Runtime source: `cf1d113cc9c4a7bbcb79b2dba5b5dfe93739ef67`
Audit report: `fdas-pr73-ruleset-defensive-readout-confirmation.json`
Report hash: `11e15b244efe7fcd43bf29bc0427b50bb74342144ad57ec0cc02e024efeaf644`

## Result

The preregistered known-opportunity confirmation passes all eight gates. The
160-turn engine game on seed `109229` completed at observed turn 161 with 271
engine actions, zero rejected actions, a valid event ledger, matching runtime
counters, and a clean frozen source identity. All 24 scalar readouts used only
`fdas-scalar-baseline-candidate-readout/1.1`.

The run produced 24 target-filtered unions, one additions-only recall, two
grounded controls, and one grounded same-target alternative. All three emitted
grounded candidates carried a compiled-ruleset defensive capability. The one
cross-type comparison passed exact unit class, defensive-effect signature,
base defense, maximum-hit-point, and firepower checks without using exact unit
name equality.

## Observed comparison

At turn 39, Alpine Troops actor 108 was the scalar control for city 118. It had
ETA 1, total movement cost 6, calibrated estimate `0.438932`, and interval
`[0.195150, 0.682714]`. Riflemen actor 124 was the protected alternative, with
ETA 3, total movement cost 18, estimate `0.427533`, and interval
`[0.192008, 0.663059]`.

Both profiles were bound to ruleset digest
`81edd60186c3b3fd048ef1fd3cb566667ab9a025d4e11d15ad689f5930ddd03b`
and had Land class, defense 4, maximum hit points 20, firepower 1, and the same
potential defensive-effect signature. Thus all five defensive-capability
predicates passed. The Riflemen route was nevertheless worse on ETA,
first-step movement cost, and total movement cost. Its calibrated interval
also overlapped the control interval. The readout therefore correctly
abstained and produced no shadow preference or action change.

This scalar role ordering differs from the earlier PR71 observation, where the
same unit types appeared in the opposite control/alternative roles. That makes
this run a useful integration confirmation but not a literal deterministic
replay of the prior candidate ordering.

## Interpretation and boundary

PR73 closes the semantic implementation defect: unit names no longer stand in
for defensive capability when the new manifest opt-in is active, and missing
or ambiguous ruleset facts still fail closed. It does not weaken route checks,
interval separation, target scope, safety filtering, or authority boundaries.

Because seed `109229` was selected from an already observed opportunity, this
result is not independent evidence. It establishes neither opportunity rate
nor ranking correctness, counterfactual outcome quality, gameplay impact,
score improvement, or win rate. The next scientific gate must use fixed unseen
seeds and should measure both cross-type comparable-candidate yield and the
frequency of interval separation before any policy experiment.
