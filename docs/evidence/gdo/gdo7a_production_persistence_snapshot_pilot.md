# GDO-7A snapshot-local production-persistence pilot

Status: predeclared; engine evaluation pending

Date: 2026-08-01

Branch: `experimental/pln-pressure–bridge–fluid`

## Purpose

The first bounded-live pilot improved queue divergence, product completion,
throughput, and mean score, but failed a predeclared gate that treated an
operation as permanently protected after any earlier guard application. RCA
showed that all 13 failures occurred only after the snapshot-local authority
correctly relinquished control for threat or upkeep-affordability safety.

This follow-on corrects the evidence contract without retuning the controller.
The veto, thresholds, safety checks, runtime flag, planner integration, and
repository defaults remain unchanged. The only implementation addition is
persisting the already-used build cost and shield stock in authority evidence
so a source-fresh audit can reconstruct later completion-bound abstentions.

## Corrected authority boundary

One guard application protects one authoritative snapshot. Until the next
`state_snapshot`, no action listed in that guard's `excluded_action_ids` may
receive an accepted `action_result`. The guard is reevaluated from scratch on
the next snapshot.

If a previously guarded operation later diverges, the last authoritative
state before its competing production switch must prove at least one declared
relinquishment reason:

- a visible enemy within radius three;
- city disorder or famine;
- negative food surplus;
- nonpositive shield surplus;
- completion beyond the 12-turn or operation-deadline bound;
- unaffordable future upkeep or negative operating gold;
- an already-changed current queue identity; or
- removal of the protected city.

Missing state, threat geometry, output, completion-bound evidence, or a
matching competing switch is not an accepted reason. It is reported as an
unattributed relinquishment and fails the pilot.

This replaces only the incoherent lifetime gate. It does not remove any
divergence from the primary metric and does not rescore the first pilot.

## Frozen cohort

| Field | Value |
| --- | --- |
| cohort | `grounded_production_persistence_snapshot_pilot_v2` |
| pairs | 30 |
| horizon | 120 turns |
| seed namespace | `pf-pln-grounded-production-persistence-snapshot-pilot-v2` |
| seed range | 8,300,000–8,399,999 |
| workers | 3 process-isolated |
| recycling | hard per arm |
| claim eligibility | false |

The seed range is disjoint from the original shadow cohort, smoke, and pilot.
The arms differ only in
`pressure_production_persistence_authority_enabled`. The source must be clean
and committed before any seed is run.

## Predeclared gates

All gates must pass:

| Gate | Required result |
| --- | ---: |
| all paired games complete | 30 / 30 |
| accepted excluded actions within a protected snapshot | 0 |
| later guarded divergences without a declared relinquishment reason | 0 |
| absolute unique divergence-rate reduction per commit | at least 0.03 |
| completion-rate delta per commit | at least 0.00 |
| completed products/game delta | at least 0.00 |
| off-scope authority rows | 0 |
| treatment engine-rejected-action rate | 0 |
| paired mean score safety floor | at least -2.0 |
| schema errors | 0 |
| baseline authority rows | 0 |
| treatment authority rows | greater than 0 |
| source-freeze gate | passed |

The audit groups divergence and completion by unique operation identity. It
does not reinterpret repeated snapshot-level blocked observations as separate
failures.

## Claim boundary

This remains a mechanism pilot. Passing would establish that the bounded
controller improves the declared production lifecycle metrics while honoring
snapshot-local safety; it would not establish a score or win-rate benefit.
The observed first-pilot score interval crossed zero, and any later score
claim requires a separately predeclared and adequately powered confirmation.

The canonical result will be written to:

```text
docs/freeciv/evidence/
gdo7a-production-persistence-snapshot-pilot-v2.json
```

