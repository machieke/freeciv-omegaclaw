# PR52d randomized alternative execution pilot preregistration

Status: frozen before execution

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

