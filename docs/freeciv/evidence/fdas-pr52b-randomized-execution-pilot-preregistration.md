# PR52b randomized alternative execution pilot preregistration

Status: frozen before execution

Corrected implementation commit: `26ae8fd`

PR52b repeats the exact PR52 one-game engineering design after correcting only
the pre-runtime startup validation order. PR52 generated no gameplay data, so
the seed, horizon, action slice, assignment policy, treatment probability,
outcome, safety stops, and all ten mechanical acceptance criteria remain
unchanged from
`fdas-pr52-randomized-execution-pilot-preregistration.md`.

The rerun must use a new output directory and `--no-resume`. It remains
claim-ineligible and excluded from every future causal fit because the
assignment key was selected to exercise the known treatment opportunity.

Frozen output directory:
`artifacts/freeciv/fdas-randomized-execution-pilot-v1-corrected`

## Frozen outcome

PR52b reached the eligible turn-17 assignment but was rejected before sending
the assigned action. The assignment selected control with draw `0.5506114`;
the engine then raised because the generic GDO operation-event adapter requires
a retained GDO payload that this independent FDAS operation does not have. No
randomized action was executed and no outcome was generated. The artifact is
preserved at the frozen output directory.

Commit `dd304be` isolates the already emitted revision-bound FDAS authority
event from the unrelated GDO payload lifecycle. It also changes the
mechanics-only assignment seed to `2`, selected from the observed exact PR52b
pair to exercise treatment. This makes the next retry explicitly unsuitable
for causal estimation, as were PR52 and PR52b.

