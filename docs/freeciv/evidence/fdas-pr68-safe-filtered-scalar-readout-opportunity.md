# FDAS PR68 safety-filtered scalar readout opportunity cohort

## Primary result

PR68 fails its frozen grounded-alternative opportunity gate. All eight fixed
games from clean commit `66d153f9f1529a78c147d2ce269cb401ccdd11ae`
completed without harness failure, infrastructure failure, rejected action, or
resume. Every game passes the complete PR67 mechanics audit, and the parent
safety-filter audit passes.

The primary report is
`fdas-pr68-safe-filtered-scalar-readout-opportunity.json`, hash
`9364021e5f06684b836ebb5ffcea22a15c4af1e7ec5a6b4e200287d1a2bbde1c`.
Its false `passed` value remains the verdict. No game may be retried or
replaced, and prior diagnostic games are not pooled into the cohort.

## Cohort result

Across 378 complete observational choice sets, the safety filter partitioned
1,035 candidates. It excluded all 645 candidates carrying
`protected-source-garrison` and admitted 390 candidates. The protected union
produced 206 readouts, 43 candidate-specific and 87 broad-backoff predictions,
and 27 calibrated additions beyond safe scalar top-1.

Safe controls were no longer rare: 50 controls grounded across five of eight
games. The full PR67 audit therefore passed, including its safe-control,
candidate-specific, source-garrison-exclusion, and safe-union gates. However,
the scalar readout recorded zero grounded alternatives, zero interval
comparisons, and zero preferences. PR68 consequently fails both its
grounded-alternative comparison gate and its game-level opportunity gate.

## Readout diagnosis

The 206 readout reasons were:

- 147 `scalar-baseline-is-not-reinforcement-move`;
- 44 `no-protected-alternative`;
- 5 `control-unestimated-or-out-of-slice`;
- 4 `control-native-route-eta-invalid`; and
- 6 `no-separated-grounded-noninferior-alternative`.

Those last six readouts each had a grounded scalar move control and one
calibrated addition. Every addition was rejected before grounding with the
single aggregate reason `pair-scope-mismatch`. No added alternative reached
the interval or grounded-noninferiority tests.

Inspection of the immutable event rows shows the scope contract is conflating
concurrent compatibility with action substitution. For example, at seed
`109111`, turn 17, the union compares two fully supported moves by Alpine
Troops actor 106 with different first-step targets. Both are alternatives for
the same reinforcement decision, but the readout rejects candidates whose
resource keys intersect the scalar baseline. Same-actor mutually exclusive
actions necessarily share their unit resource, so this rule structurally
prevents that kind of decision-safe comparison.

This is not evidence that the rejected alternative was better. It establishes
only that a coarse pair-scope predicate censored every observed comparison
opportunity before grounded evaluation.

## Next scientific gate

Do not relax source-garrison safety, target-objective identity, operation type,
or bounded grounding. First version the scope diagnostic so every conjunct is
reported separately: duplicate action, operation-type mismatch, target-ref
mismatch, identical resource set, and resource overlap. Then define a
protected substitution contract that allows shared actor resources only for
mutually exclusive candidate actions serving the same grounded target and
operation type. Other shared resources must remain fail-closed.

That correction requires a separate preregistered fresh smoke. PR68 remains a
failed primary result and cannot be reinterpreted as a comparison, ranking,
gameplay, score, or win-rate claim.

## Claim boundary

PR68 confirms safety-filter mechanics and reliable safe-control yield, but it
does not establish any grounded protected-alternative comparison. It grants no
policy, action-selection, truth, readout, flow, or capacity authority and makes
no counterfactual, gameplay, score, or win-rate claim.
