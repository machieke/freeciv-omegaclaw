# FDAS PR65 protected scalar-baseline readout smoke

## Primary result

The PR65 smoke is mechanically accepted but fails its frozen comparison-yield
gate. Clean commit `ef745bb` ran fixed seed `109009` to a genuine terminal at
observed turn 152 with zero infrastructure failures, rejected actions, or
resumes. Every event and counter binding is valid and warning-free, the exact
profile, manifest, source, model, artifact, and confirmation are bound, and no
legacy-control readout or undeclared authority appears.

The primary report is
`fdas-pr65-scalar-baseline-readout-smoke.json`, hash
`5f6416d4d53d4800865773f905f440816259c2eeebaab8426c8ff3ac21e30cec`.
Its `passed` value is false and remains the verdict.

## Yield

The run produced 82 choice sets, union events, and scalar-baseline readouts.
Every union contained exactly one scalar member and one candidate readout, so
there were zero calibrated additions and no protected alternative to compare.
The model still produced 73 candidate-specific move estimates: 47 `full`, 24
`eta`, and two `route` estimates. Nine scalar baselines were fortify actions
and correctly abstained outside the move-only model domain.

All 82 scalar-baseline readouts abstained. The nine fortify controls reported
`scalar-baseline-is-not-reinforcement-move`. The 73 estimated move controls
reported the generic `control-grounded-transition-input-unavailable`. Thus the
required `grounded_protected_alternative_compared` gate failed, with zero
grounded alternatives, interval overlaps, or preferences.

## Interpretation and next gate

PR65 confirms that the new event, control identity, parent binding, counters,
and fail-closed mechanics work. It does not close the intended comparison gate.
The fresh seed offered no protected competition, so it cannot be retried or
replaced post hoc.

It also exposes an independent observability mismatch that must be resolved
before sizing a larger cohort: every move query had complete PR59 transition
grounding and a supported candidate-specific estimate, yet the stricter
decision grounding collapsed all controls into one generic unavailable reason.
The strict validator additionally checks current legality, operation/goal and
deficit support, exact native-route authority, action/resource/blocker shape,
and unit fields. A prospective hardening should report the exact failed
predicate while keeping abstention and all authority unchanged. A multi-game
opportunity cohort should be designed only after this cause is measurable;
otherwise candidate opportunity and grounding failures would be confounded.

## Claim boundary

This failed smoke makes no preference, ranking, counterfactual, gameplay,
score, or win-rate claim. It grants no activation authority and cannot be
pooled with a future corrected or larger cohort.
