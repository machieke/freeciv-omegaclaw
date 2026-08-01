# GDO-7A snapshot-local production-persistence pilot

Status: completed; all 13 corrected mechanism gates passed

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

## Engine result

The source-frozen implementation at commit
`c17d7d85769039aa138e384d6c6e98fb67251ae9` completed all 30 fresh
pairs and 60 arms with hard server recycling, zero infrastructure failures,
and a passing source-freeze gate. The strict audit validated 396,093 events
with zero schema errors or warnings.

| Observation | Baseline | Treatment | Delta |
| --- | ---: | ---: | ---: |
| committed production operations | 379 | 360 | -19 |
| completed products | 299 | 305 | +6 |
| completed products/game | 9.967 | 10.167 | +0.200 |
| completion rate/commit | 78.89% | 84.72% | +5.83 points |
| unique queue divergences | 60 | 29 | -31 |
| divergence rate/commit | 15.83% | 8.06% | -7.78 points |
| persistence authority rows | 0 | 3,914 | +3,914 |
| uniquely guarded operations | 0 | 272 | +272 |
| off-scope authority rows | 0 | 0 | 0 |
| engine-rejected-action rate | 0 | 0 | 0 |

No accepted competing production switch occurred before the next
authoritative snapshot for any of the 3,914 guard applications. Nine guarded
operations later diverged after the guard was reevaluated and relinquished
authority. All nine have an authoritative reason: five had negative food,
three had a visible threat within radius three, and one exceeded the declared
completion bound. None was unattributed.

All 13 corrected gates passed. This reproduces the first pilot's directional
mechanism effect under a contract that exactly matches the controller's
snapshot-local safety boundary. The authority remains repository-default-off:
the result proves a bounded production-continuity mechanism, not that enabling
it generally improves gameplay score.

## Score boundary

Mean score was 129.7 in baseline and 130.6 in treatment. The paired mean
delta was +0.9 with a 95% paired-bootstrap interval of [-0.3, 2.5]; the exact
two-sided paired randomization p-value was 0.359375. Fixed-horizon score lead
was 2/30 in baseline and 3/30 in treatment, a paired risk difference of
+3.33 points with only one discordant pair and an exact McNemar p-value of
1.0.

The cohort was deliberately `claim_eligible: false` and achieved an estimated
76.8% power for a +2 score-point target. It therefore supports no score or
win-rate claim. The aggregate recommends at least 33 fresh pairs for a
separately frozen score confirmation under the observed variance; win-rate
confirmation would require a much larger design.

## Canonical evidence

The canonical audit is:

```text
docs/freeciv/evidence/
gdo7a-production-persistence-snapshot-pilot-v2.json
```

Canonical hashes:

```text
audit semantic hash:
958e6fd15c1784375baba807aaeb334c1ab5af78500274c56a4eddc4886aed06
audit file SHA-256:
b6d40c808ebcafd75834e3f49754fac9a07be805cb78fd59ed64b44d6f2ccec6
aggregate file SHA-256:
77854ac553eb21ab7d3748f2e28d3ed9c6af54f3f4303aa5b41a2351b6d7e521
```
