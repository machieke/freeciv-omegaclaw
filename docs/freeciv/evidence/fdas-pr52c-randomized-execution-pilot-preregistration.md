# PR52c randomized alternative execution pilot preregistration

Status: frozen before execution

Corrected implementation commit: `dd304be`

PR52c repeats the PR52 mechanical criteria after two pre-action failures. PR52
failed before runtime construction; PR52b reached assignment but failed before
action send. Neither produced randomized outcomes.

All PR52 inputs and acceptance criteria remain unchanged except:

- assignment seed is `2`;
- the FDAS authority assignment is the operation-selection authority event;
  the generic GDO retained-payload event is correctly not required;
- frozen output directory is
  `artifacts/freeciv/fdas-randomized-execution-pilot-v1-event-isolated`.

The seed was chosen after observing the exact PR52b pair and is expected to
produce treatment draw `0.2637811`. This run is a deliberately targeted
mechanics exercise, claim-ineligible, and permanently excluded from causal
fitting or performance evaluation.

## Frozen outcome

PR52c successfully selected treatment, rematerialized actor `117`, passed the
final execution gate, and received an accepted engine action result. It then
failed while emitting the execution/episode link because the episode revision
had already replaced the assignment revision in the live FDAS store. No
delayed outcome was completed. The artifact is preserved at the frozen output
directory.

Commit `141e880` emits the accepted execution link after the episode is durably
created but before publishing its same-snapshot episode projection. This keeps
the authority event bound to its exact assignment revision and makes the next
causal event the episode-revision publication.

