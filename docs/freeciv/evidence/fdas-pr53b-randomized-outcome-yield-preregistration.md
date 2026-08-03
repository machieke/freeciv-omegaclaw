# PR53b corrected fresh-seed randomized outcome-yield preregistration

Status: mechanically rejected; progression failed

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

## Frozen outcome

PR53b executed all 12 frozen seeds from clean source commit `30c4b45` with one
implementation digest. Runtime was 1,047.72 seconds. Eight games completed, but
only seven reached the fixed endpoint: seed `105613` ended at turn 152. Four
games were mechanically rejected:

- `105503`, `105557`, and `105607` raised
  `candidate choice set identity collision`;
- `105529` raised
  `exact rematerialization requires one cached candidate` after two treatment
  assignment events.

Audit 1.3 retains all three raw treatment events but excludes the two events
from failed seed `105529` from every outcome statistic. The only analyzable
assignment was treatment on seed `105509` at turn 111. Its exact action was
accepted and linked to one episode and one due-turn-143 label, which resolved
positive. Thus the analyzable result is one positive treatment outcome in one
game, zero controls, no risk-difference estimate, and a treatment Wilson
interval of `[0.2065, 1.0]`. This fails both the mechanical and two-independent-
games-per-arm progression gates and supports no candidate-value or gameplay
claim.

The machine-readable rejected report is
`fdas-pr53b-randomized-outcome-yield.json`, report hash
`a1618c0a71d006a73562e242513ba098e47caa07f4fa53728e8cf16e32d8a869`.
Commit `db11226` binds choice-set identity to every immutable field, permits a
validated byte-identical defense action to be reprojected through the normal
bounded operation-authority path when the legacy catalog is narrower, rejects
actions outside the authority kind, and makes early failed games auditable as
explicitly rejected rows. PR54 replays the four exact failure seeds for
mechanics only before any new fresh-seed yield attempt.
