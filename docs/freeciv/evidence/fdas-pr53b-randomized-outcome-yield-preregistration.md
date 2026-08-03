# PR53b corrected fresh-seed randomized outcome-yield preregistration

Status: preregistered; execution not started

Implementation commit: `caf9010bfdb67a0cb0acb37ad165b7fd75153559`

## Purpose and frozen inheritance

PR53b repeats the exact claim-ineligible design, seeds, assignment policy,
outcome, missingness rules, clustering rules, stopping rules, mechanical gates,
and scientific progression rule preregistered in
`fdas-pr53-randomized-outcome-yield-preregistration.md`.

PR53 failed before any gameplay because the launch omitted the required local
ruleset environment binding. Its 12 manifests contain only the shared startup
error: there are no event ledgers, engine states, action pairs, randomized
assignments, or outcomes. Reusing the frozen seed list therefore does not
condition PR53b on gameplay or intervention data.

## Sole correction

PR53b adds the already documented local engine bindings:

```text
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002
FREECIV_API_TOKEN=<local proxy token>
FREECIV_SERVER_CONTAINER=fciv-net
```

The proxy token remains process-local and must not be copied into an artifact,
manifest, event, report, or repository file. No controller, FDAS, gameplay,
seed, endpoint, assignment, audit, or analysis setting changes.

The corrected frozen output is
`artifacts/freeciv/fdas-randomized-outcome-yield-v1-corrected`. It is created
from scratch with `--no-resume`; the rejected PR53 output remains immutable.
The execution source must be the clean documentation-only descendant containing
this correction, with one identical implementation digest across all games.

## Decision rule

All PR53 mechanical and progression criteria remain binding without revision.
If PR53b fails, it is preserved and reported. If it passes mechanically, its
observed independent game-cluster yield—not the direction of its descriptive
effect—determines whether a powered discovery cohort is feasible.
