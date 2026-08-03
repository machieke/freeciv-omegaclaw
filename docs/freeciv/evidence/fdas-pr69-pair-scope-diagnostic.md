# FDAS PR69 scalar pair-scope diagnostic cohort

## Primary result

PR69 fails its frozen exact-scope opportunity gates. All eight fixed games from
clean commit `5b854f5c8512a2408db2407b2bed346fc8aca76a` completed with
zero harness failures, infrastructure failures, rejected actions, or resumes.
The complete parent PR67 safety-filter audit passes.

The primary report is `fdas-pr69-pair-scope-diagnostic.json`, hash
`6cc6ebfcbd761577fac824d59b4c48d4a3a58ac42da7be473b60ea01fbfd3611`.
Its false `passed` value remains the verdict. No seed is retried or replaced.

## Result

The cohort partitioned 634 observational candidates, excluded all 528
source-garrison-unsafe candidates, admitted 106 safe candidates, and emitted
97 protected unions. It produced 26 candidate-specific predictions, four
broad-backoff predictions, four calibrated additions, and five grounded scalar
controls.

Unlike PR68, the additions and grounded move controls never coincided in the
same readout. The 97 terminal readout reasons were:

- 71 `scalar-baseline-is-not-reinforcement-move`;
- 19 `control-native-route-eta-invalid`;
- 5 `no-protected-alternative`; and
- 2 `control-unestimated-or-out-of-slice`.

No readout reached pair-scope evaluation. Thus zero legacy generic reasons is
mechanically correct, but no exact predicate or resource overlap was observed.
Those two required opportunity gates fail.

## Interpretation and next gate

The diagnostic code remains fail-closed and its synthetic tests prove exact
reason emission, but this fresh cohort cannot establish live exact-reason
yield. The PR68 descriptive three-of-eight contributing-game rate did not
replicate in the next eight games. This demonstrates that the event is too
sparse or nonstationary for repeated seed consumption to be an efficient
diagnostic strategy.

Do not append games to PR69. The next bounded step is a separately identified,
post-hoc sensitivity that reconstructs exact scope predicates for PR68's six
already-observed pairs from its immutable, hash-bound union events and candidate
choice-set records. That can diagnose the stored rows deterministically, but it
cannot make PR69 pass or serve as fresh confirmation.

## Claim boundary

PR69 establishes parent safety mechanics and a negative exact-scope opportunity
result only. It does not justify scope relaxation or make an alternative-
grounding, ranking, counterfactual, gameplay, score, or win-rate claim. All
policy, readout, truth, flow, capacity, and action-selection authority remains
unchanged.
