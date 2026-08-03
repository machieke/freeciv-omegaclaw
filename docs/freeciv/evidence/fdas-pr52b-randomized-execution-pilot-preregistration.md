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

