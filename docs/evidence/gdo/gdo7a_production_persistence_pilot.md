# GDO-7A bounded production-persistence pilot

Status: predeclared; engine evaluation pending

Date: 2026-08-01

Branch: `experimental/pln-pressure–bridge–fluid`

## Hypothesis and attribution boundary

The fresh shadow cohort observed 11 unique production operations whose exact
queue target diverged after an accepted queue selection and before the
declared product appeared. This pilot tests one narrow hypothesis: when an
active operation is safe and close to completion, preventing a competing
production switch reduces that divergence without reducing completed product
throughput.

The treatment does not inject an action, select a product, extend an operation
deadline, reserve new capacity, change bridge/flow behavior, or modify the
research controller. It may only remove other currently advertised
`city_production` actions for the same city from one planner readout. Every
non-production action and the byte-identical current queue action remain
available. The existing planner still selects the winner.

Research remains a shadow-only comparator in both arms. This preserves clean
attribution to production continuity rather than combining two new authority
paths.

## Default-off authority contract

The behavior-changing flag is
`pressure_production_persistence_authority_enabled`; its repository default is
`false`. Enabling it also requires the scalar PF-v2 semantics, operation
lifecycle, production operations, and commit revalidation. It is rejected in
combination with the other experimental winner-changing authority layers.

The veto is permitted only when all of these conditions are observed in the
same authoritative snapshot:

1. exactly one production operation is active for the city;
2. the operation is waiting on its product-observation step;
3. its exact kind/value target is still the current queue target;
4. the city is neither in disorder nor marked as having famine;
5. food surplus is nonnegative and shield surplus is positive;
6. no visible enemy is within radius three of the city;
7. constant-current-rate completion is at most 12 turns away and within the
   operation deadline;
8. any compiled future upkeep is affordable from current gold and current
   operating gold is nonnegative; and
9. at least one different, currently advertised production action exists for
   that exact city slot.

Missing or ambiguous lifecycle, identity, city, map, economy, upkeep, output,
threat, or deadline information causes abstention. Each actual application
emits an `operation_step_selected` event with the excluded action hashes,
protected city, completion bound, full safety readout, and authority
provenance. The audit rejects any authority event outside this contract.

## Frozen cohorts

The source is committed and clean before either cohort starts. Both cohorts
use hard server recycling per arm and the existing 120-turn finalization
contract.

| Cohort | Purpose | Pairs | Seed namespace | Seed range |
| --- | --- | ---: | --- | --- |
| `grounded_production_persistence_smoke_v1` | confirm live activation and evidence shape | 1 | `pf-pln-grounded-production-persistence-smoke-v1` | 8,100,000–8,199,999 |
| `grounded_production_persistence_pilot_v1` | mechanism pilot | 30 | `pf-pln-grounded-production-persistence-pilot-v1` | 8,200,000–8,299,999 |

The paired arms are identical except for the persistence-authority flag. The
pilot seeds are not used to tune thresholds or select a replacement mechanism.
If the implementation cannot activate in the smoke cohort, it may be repaired
before the pilot while the pilot seeds remain unseen. After the pilot begins,
any correction requires a separately named cohort and disjoint seed range.

## Predeclared mechanism gates

The pilot passes only if all 30 pairs complete and every condition below is
true:

| Gate | Required result |
| --- | ---: |
| absolute unique queue-divergence rate reduction per committed operation | at least 0.03 |
| completion-rate delta per committed operation | at least 0.00 |
| completed products per game delta | at least 0.00 |
| guarded operations that later diverge | 0 |
| off-scope authority rows | 0 |
| treatment engine-rejected-action rate | 0 |
| paired mean score delta safety floor | at least -2.0 |
| schema errors | 0 |
| baseline persistence-authority rows | 0 |
| treatment persistence-authority rows | greater than 0 |
| source-freeze gate | passed |

The primary metric counts unique operation identities, not repeated
snapshot-level block observations. Completion and throughput are co-primary
safety checks because suppressing all switches would trivially reduce one
kind of divergence while potentially preserving a bad product.

## Claim boundary

Both cohorts are `claim_eligible: false`. A passing pilot establishes only
that this bounded readout improves its declared production-lifecycle mechanism
metric without violating its safety floors. Thirty 120-turn pairs do not
establish a general score or win-rate improvement. Failure is retained as a
negative result; the thresholds will not be changed after observing the pilot.

The canonical post-run audit will be written to:

```text
docs/freeciv/evidence/gdo7a-production-persistence-pilot-v1.json
```

