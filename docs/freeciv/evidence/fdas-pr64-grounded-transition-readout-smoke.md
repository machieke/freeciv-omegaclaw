# FDAS PR64 grounded-transition readout smoke

## Result

The corrected PR64 engine smoke passes from clean commit
`d33bea62c790a527c0c44507a3dc19fedc6fb0ac`. Fixed seed `109007` reached
observed turn 161 with zero infrastructure failures, rejected actions, or
resumes. The warning-free event ledger, exact profile and manifest, source
identity, PR60 model, PR60 artifact, and PR63 confirmation bindings all pass
the frozen audit.

Report `fdas-pr64-grounded-transition-readout-smoke.json` passes with hash
`3febbfd118abdf57e6828f3099fc647381eac6df2da8687c096a44f91eee07ff`.
Engine latency was 189.67 seconds.

## Readout yield

Across 135 choice surfaces, the protected union recorded 582 candidate
readouts. The grounded-transition model estimated 458 move candidates and all
458 used candidate-specific levels rather than broad action/lifecycle backoff:

- 355 `eta` estimates;
- 95 `eta-lifecycle` estimates;
- 3 `full` estimates;
- 3 `compact-lifecycle` estimates; and
- 2 `full-lifecycle` estimates.

The two `full-lifecycle` intervals exceeded the frozen width gate. All 124
fortify candidates correctly abstained as outside the move-only model domain.
The resulting 126 uncertainty/domain abstentions and 456 confidence-eligible
move readouts formed 155 protected members and added 20 candidates beyond
scalar top-1. No flow, capacity solver, truth, policy, readout, or action-
selection authority was present.

## Decision-safe result and next bottleneck

All 135 decision-safe evaluations honestly abstained and no action changed.
This was not caused by broad calibration or interval overlap:

- 128 selected live actions had no unique matching FDAS reinforcement route;
- 4 selected actions were not reinforcement moves;
- 2 matched controls lacked a complete grounded transition input; and
- 1 matched control was unestimated or outside the eligible slice.

No evaluation reached a grounded control/alternative interval comparison, so
there were zero interval-overlap abstentions and zero diagnostic preferences.
PR64 therefore closes the load, binding, candidate-specific prediction, and
protected-union mechanics gate, while identifying control alignment as the
next semantic bottleneck. The existing readout is anchored to the selected
legacy action even though the calibrated union's protected baseline is its
scalar top-1 FDAS candidate. A prospective correction must decide and freeze
which control answers the scientific question before collecting more games;
rerunning the current readout or loosening uncertainty cannot resolve this
mismatch.

## Claim boundary

This result establishes default-off shadow mechanics and recurrent candidate-
specific readout/union yield only. Nonselected outcomes remain censored. It
does not establish calibrated cross-candidate ranking, counterfactual value,
gameplay impact, score, or win rate, and it grants no activation authority.
