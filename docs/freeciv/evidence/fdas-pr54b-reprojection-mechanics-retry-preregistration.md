# PR54b exact reprojection mechanics retry preregistration

Status: passed; exact reprojection mechanics proven

Implementation commit: `153f4be5845e81b064d01467c9770a26571316f3`

## Purpose and claim boundary

PR54b is a deliberately post-hoc, claim-ineligible engineering retry. It uses
historical seed `105529` and the two exact action pairs observed in PR54 to make
the previously ambiguous catalog path measurable. It cannot contribute to
opportunity yield, candidate value, gameplay, score, or win-rate estimation.
Its sole question is whether an assigned action outside the cached legacy
catalog can be reprojected through the bounded city-defense authority path,
accepted by the engine, and attributed downstream without broadening authority.

## Frozen intervention

The controller, horizon, gameplay seed, legal-action gates, resource checks,
packet checks, outcome target, and treatment probability remain unchanged.
The only intervention is a separate manifest with:

- experiment ID `fdas-reprojection-mechanics-retry-v1`;
- randomization seed `1`; and
- execution event version 1.1 reprojection provenance enabled.

Those values were chosen after observing PR54. For its frozen turn-37 and
turn-39 action pairs, independently reconstructed draws are `0.6171186461`
(control) and `0.4393403992` (treatment). Selecting the seed this way is valid
for targeted path coverage only and permanently excludes the run from any
causal or yield analysis. If upstream deterministic action identity differs,
the actual exogenous draw remains authoritative; the run is not edited or
resumed to obtain a favorable path.

| Input | Value |
|---|---|
| Config | `profile/freeciv_harness_fdas_reprojection_mechanics_retry_160_turn.yaml` |
| Seed | `105529` |
| Horizon | 160 turns |
| Backend | `engine-live` |
| Condition | `e_full_loop` only |
| Manifest | `profile/fdas_manifest_defense_alternative_collection_reprojection_retry.json` |
| Assignment policy | `fdas-defense-nearest-score-randomized/4.0`, probability `0.5` |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |
| Audit | `fdas-randomized-alternative-live-audit/1.4` |
| Output | `artifacts/freeciv/fdas-reprojection-mechanics-retry-v1` |

The launch must use a clean documentation/configuration descendant of the
implementation commit, `--limit-seeds 1`, and `--no-resume`. The harness
requires every syntactically valid config to contain at least 30 unique seed
entries; `105529` is first and the remaining 29 entries are inert validation
fillers excluded by the frozen limit.

## Acceptance criteria

PR54b passes only if:

1. seed `105529` reaches the fixed endpoint without infrastructure failure or
   a rejected engine action;
2. at least one randomized treatment assignment is accepted and linked once to
   its exact episode, choice set, and due-turn outcome lifecycle;
3. at least one linked execution event contains typed
   `authority_catalog_reprojected: true`, and the aggregate status counter
   equals the number of such events;
4. the event ledger and persisted stores are valid, hash-consistent, and not
   quarantined; and
5. no truth, claim, score, flow, advection, capacity, unrelated action, or
   non-city-defense authority is introduced.

Failure is preserved as evidence. A pass authorizes only a new preregistered
unseen-seed yield cohort; it does not rehabilitate PR53b or PR54 outcomes.

## Frozen result

PR54b passed every preregistered engineering gate. Seed `105529` ran from clean
source commit `13e522d` with implementation digest
`49067650358ee3c6916b2b1d1223c01c6e8d1c85c7c5594f596ad0e00d460433`,
reached final observed turn 161 in 86.69 seconds, and completed with no
infrastructure failure or rejected engine action.

The exact assignments were:

| Turn | Draw | Arm | Reprojected | Engine | Due label |
|---:|---:|---|---|---|---|
| 37 | 0.7117420215 | control | false | accepted | turn 69, negative |
| 39 | 0.4393403992 | treatment | true | accepted | turn 71, negative |

The turn-39 treatment selected the historical actor-`113` move to `(7,15)`.
Its execution event version 1.1 records
`authority_catalog_reprojected: true`; the run status records exactly one
catalog reprojection. The accepted action links through one exact episode, one
selected choice set, and one observed due-turn label. The ledger validates with
no warnings, all stores are digest-valid and unquarantined, and every audit 1.4
gate passes.

The machine-readable report is
`fdas-pr54b-reprojection-mechanics-retry.json`, report hash
`b274897122442de93a9bda7fd04fdf58d1eb72d33f77552bbfea998e614a348a`.
Both outcomes were negative, but that direction is scientifically
non-interpretable because the assignment seed was selected after observing the
action pairs. The result proves only bounded reprojection, legal execution, and
attribution mechanics. It now permits a separately preregistered unseen-seed
opportunity-yield cohort.
