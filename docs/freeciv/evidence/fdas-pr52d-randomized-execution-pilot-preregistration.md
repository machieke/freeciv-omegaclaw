# PR52d randomized alternative execution pilot preregistration

Status: executed; mechanically rejected on delayed-label completeness

Corrected implementation commit: `141e880`

PR52d repeats the exact PR52c mechanics-only design after moving the accepted
execution-link event before same-snapshot episode projection. PR52c proved that
the treatment assignment, exact cached-candidate rematerialization, final gate,
and engine acceptance all work; it produced no completed delayed outcome.

Inputs, assignment seed `2`, horizon, safety stops, and acceptance criteria are
unchanged. The new frozen output directory is:

`artifacts/freeciv/fdas-randomized-execution-pilot-v1-revision-ordered`

Like all PR52 attempts, this targeted mechanics run is claim-ineligible and
excluded from causal fitting and performance evaluation.

## Frozen outcome

The game completed the 160-turn horizon with 414 accepted and zero rejected
engine actions. One eligible assignment selected treatment at turn 17,
changed actor `112` to actor `117`, passed exact rematerialization and the
final gate, and linked the accepted result to exactly one decision episode and
choice set with the assignment hash, arm, `0.5` propensity, authority, and
`claim-eligible:false` intact.

PR52d nevertheless fails criterion 9. The treatment's first route step had an
attributed movement effect but no immediate goal relief, so the legacy label
opener never created its 32-turn selected-actor label. The choice set remained
`pending-observation` without a valid due turn. This is a selection-dependent
missing-outcome mechanism: alternatives with no immediate relief could be
systematically absent from the randomized outcome data. The completed artifact
is preserved unchanged at the frozen directory and is excluded from fitting,
evaluation, and all value or performance claims.

Commit `6774edd` corrects the lifecycle by indexing the selected-actor target
at every accepted in-scope selection, persisting the selection turn in the
episode, and opening its restart-safe label immediately rather than waiting
for relief.
