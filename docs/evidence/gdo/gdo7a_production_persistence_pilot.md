# GDO-7A bounded production-persistence pilot

Status: completed; 12 of 13 gates passed, overall mechanism gate failed

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

## Engine result

The source-frozen implementation at commit
`0148f2ae7b2718232e42d8a31d5a4e47ba165a4c` first passed the one-pair smoke:
both arms completed, treatment emitted 131 in-scope authority rows over nine
unique operations, baseline emitted none, schema validation was clean, and
the guarded arm improved both divergence and completion on that diagnostic
seed. The smoke result was not used to change the pilot design.

The fresh pilot then completed all 30 pairs and 60 arms with hard server
recycling, zero infrastructure failures, and a passing source-freeze gate.
The canonical audit validated 419,358 events with zero schema errors or
warnings.

| Observation | Baseline | Treatment | Delta |
| --- | ---: | ---: | ---: |
| committed production operations | 359 | 353 | -6 |
| completed products | 278 | 303 | +25 |
| completed products/game | 9.267 | 10.100 | +0.833 |
| completion rate/commit | 77.44% | 85.84% | +8.40 points |
| unique queue divergences | 55 | 30 | -25 |
| divergence rate/commit | 15.32% | 8.50% | -6.82 points |
| persistence authority rows | 0 | 3,829 | +3,829 |
| uniquely guarded operations | 0 | 262 | +262 |
| off-scope authority rows | 0 | 0 | 0 |
| engine-rejected-action rate | 0 | 0 | 0 |

The paired mean score delta was +0.9 with a paired-bootstrap interval of
[-0.867, 3.2]. The exact two-sided paired randomization p-value was 0.5. This
is neither statistically significant nor claim-eligible, and the cohort was
not powered as a score confirmation.

Twelve of the 13 predeclared gates passed. The sole failure was
`guarded_operations_do_not_diverge`: 13 of the 262 operations that had been
guarded at least once later diverged, exceeding the declared maximum of zero.
The pilot therefore failed overall despite the positive mechanism deltas.

## Failed-gate RCA

The failed gate was retained unchanged. A post-hoc trace diagnosis found:

- every one of the 13 operations was protected only on an earlier snapshot;
- no competing same-city production action was accepted on a snapshot where
  the guard was active;
- all 13 later snapshots contained an explicit competing production switch;
- 11 switches occurred after a visible enemy entered the declared radius
  three, causing the guard to abstain as designed; and
- the other two occurred after operating gold became negative while the
  protected product carried future upkeep, also causing required abstention.

This identifies a mismatch between the zero-tolerance gate and the bounded
authority contract. The guard is intentionally snapshot-local and must yield
when threat or affordability becomes unsafe. The gate instead treated an
operation as permanently protected after any earlier safe application. Making
the implementation satisfy that gate would require overriding its declared
threat/economy safety rules, so the implementation is not changed to chase it.

This RCA is explanatory only. It does not convert the failed pilot into a pass
or remove the 13 rows from the canonical result.

## Decision and next evidence boundary

The new authority remains default-off. The run supports a strong directional
mechanism result but no production-authority, score, or win-rate claim.

A fresh follow-on may test the same frozen controller with a corrected,
predeclared safety metric:

1. zero accepted competing same-city production switches on snapshots where
   the guard is active;
2. every later relinquishment attributed to a persisted threat, economy,
   disorder/famine, ETA/deadline, ambiguity, or identity reason;
3. the same divergence-reduction, completion, throughput, engine-safety, and
   score-floor gates; and
4. a new cohort name and disjoint seeds.

That follow-on must remain distinct from a score confirmation. If it passes,
a separately powered confirmatory score cohort would still be required.

Canonical hashes:

```text
audit semantic hash:
3aa0cec94928286973e176f66c228450020c3e1e18b628891e375f44fd0d7fa5
audit file SHA-256:
c475006a0f84db6d5c317ae0eb3616af4f19ae6cc79ff7575a19bb0f582c259d
aggregate file SHA-256:
32fc308b3a23f2a9c12d78314addd09deb77d54276f3e1f654264b140c0c40c6
```
