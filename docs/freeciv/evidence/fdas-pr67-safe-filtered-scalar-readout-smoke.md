# FDAS PR67 safety-filtered scalar readout smoke

## Primary result

PR67 is mechanically accepted but fails two frozen safe-control yield gates.
Clean commit `fa20a0a` ran fixed seed `109031` to observed turn 161 with zero
infrastructure failures, rejected actions, or resumes. Every filter, union,
readout, causal-parent, source, manifest, model, counter, and event-ledger gate
passes without warning.

The failed primary report is
`fdas-pr67-safe-filtered-scalar-readout-smoke.json`, hash
`e8c901a1731eaa8bb2802cf49877c759975fff76e243b59706e4381ba9666072`.
Its false `passed` value remains the verdict.

## Safety-filter result

The run emitted 80 filter events over all 126 observational candidates. The
filter excluded 122 move candidates; every one carried
`protected-source-garrison` plus `uncompiled-action-effect` and returned
`candidate-has-noncontractual-blockers`. None entered a union. Four fortify
candidates with only the permitted `uncompiled-action-effect` blocker passed
the bounded fortification validator.

Seventy-six surfaces had no safety-eligible candidate and correctly emitted no
union. The four safe fortify surfaces formed four one-member unions, then
abstained as `scalar-baseline-is-not-reinforcement-move`. Consequently:

- source-garrison exclusion and safe-union mechanics passed;
- no unsafe candidate became eligible or appeared in a union;
- no safety-eligible move received a candidate-specific union estimate; and
- no safety-filtered reinforcement control was grounded.

The latter two preregistered gates failed. There were no alternatives,
interval comparisons, or preferences.

## Interpretation and next gate

PR67 fixes the correctness defect: unsafe source-city removals can no longer
become calibrated controls or alternatives, while the full choice surface is
still recorded. The remaining failure is opportunity yield. PR66 observed two
grounded safe move controls in one game; PR65 and PR67 observed none, an
empirical one-of-three contributing-game rate. This tiny descriptive rate is
not a performance claim, but it can prospectively size an engineering cohort.

At an assumed one-third contributing-game probability, eight independent
fresh games have `1 - (2/3)^8 = 0.961` probability of containing at least one
such game. A separate eight-game cohort should freeze all seeds and require at
least one grounded protected alternative comparison, without requiring a
preference. PR65–PR67 cannot be pooled into that cohort.

## Claim boundary

PR67 establishes mechanically correct safety exclusion on one game but fails
safe reinforcement yield. It makes no preference, ranking, counterfactual,
gameplay, score, or win-rate claim and permits no action authority.
