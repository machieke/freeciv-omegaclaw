# GDO-5 material-aware combat engine pilot

Date: 2026-07-31

Branch: `experimental/pln-pressure–bridge–fluid`

Authority: bounded `attack_then_conditional_attack` authority in the treatment
arm only

Claim status: fresh bounded-mechanism pilot passed; no score or win-rate claim

## Frozen cohort

`combat_operation_material_authority_pilot_v1` was committed before execution
and used 30 paired seeds disjoint from the preceding diagnostic.

- 160-turn `civ2civ3` high-contact scenario;
- three controller workers;
- baseline and treatment differed only in
  `pressure_combat_operation_authority_enabled`;
- clean source required at
  `9c7a072279155320b4aab01e6e54e4005fa7c05a`;
- 60/60 arms and 30/30 pairs completed;
- zero game or infrastructure failures;
- one implementation digest and one commit across every arm;
- paired initial-state fidelity passed;
- 2,059,020 events validated with zero errors and zero warnings.

The raw 4.65 GiB corpus is retained outside Git at
`/data/freeciv/gdo5-combat-material-authority-pilot-v1`. The self-hashed audit
is `benchmarks/gdo/gdo5_combat_material_engine_pilot.json`, report hash
`3661006e7fb53fb3db2f1cd0674c624070a58843d0d78c9ed91166c80c58278b`.

## Predeclared mechanism result

| Metric | B1 baseline | Material authority | Delta |
| --- | ---: | ---: | ---: |
| Selected operations | 94 | 104 | — |
| Activated operations | 42 | 94 | — |
| Activation / selection | 44.68% | 90.38% | +45.70 pp |
| Completion / selection | 78.72% | 91.35% | +12.62 pp |
| Adverse terminal / selection | 21.28% | 8.65% | −12.62 pp |
| Completion / activation | 100% | 100% | 0 pp |
| Partial activations | 0 | 1 | gate failed |
| Hard-current reservation conflicts | 0 | 0 | pass |
| Selected-target conflicts | 0 | 0 | pass |
| Non-positive material activations | 0 | 0 | pass |

All 94 treatment authority rows were the declared operation and action type.
The captured replay still establishes lower duplicated targeting than the
independent B1 readout. Positive-sample treatment scheduler p95 was 17.99 ms,
below both the predeclared 50 ms ceiling and the 20 ms scheduler budget.

Immediate terminal-loss observations were uncensored. The
treatment-minus-baseline expected-versus-realized residual shift was
`+0.6430` shield-equivalent points per committed step, inside the predeclared
maximum adverse shift of `1.0`.

The pilot nevertheless failed. Safety gates are conjunctive; one partial
activation is sufficient to reject the mechanism.

## Failure and correction

The failing operation had two required actors. Before activation, a later
step became non-positive and the whole operation entered `blocked`. The
repair path subsequently grounded and reserved only the current step, while
the immutable operation contract still named both required participants.
That allowed the operation to activate with one of two actor claims.

The lifecycle now separates the two repair cases:

- before the first activation, every remaining step must be grounded and the
  whole-operation claim set must be reserved atomically;
- after activation, step-only re-estimation remains allowed for the
  conditional follow-up.

A focused regression reproduces block/recovery before activation and requires
both actor claims plus the two-action budget before the state can return to
`reserved`. The combat lifecycle and cohort-audit suites pass 26/26 after the
correction.

The correction was developed after observing the pilot and therefore cannot
retroactively change its result. Any confirmation must use fresh, disjoint
seeds and a newly frozen source commit.

`combat_operation_material_atomic_repair_pilot_v1` is that fresh checkpoint:

- 30 paired seeds in the disjoint 6.5M range;
- the same isolated 160-turn scenario and authority flag;
- the original predeclared 1.0 shield-equivalent adverse residual tolerance;
- zero partial activation remains a conjunctive release gate;
- no post-run score eligibility.

It is labeled a new pilot, rather than a confirmation, because its lifecycle
implementation differs from the failed pilot.

## Fresh atomic-repair pilot result

The fresh pilot ran from clean source commit
`c31c5ee5c8965be86d0773f4352cb8bafd815248`:

- 60/60 arms and 30/30 disjoint pairs completed;
- zero game or infrastructure failures;
- one implementation digest and one commit across every arm;
- paired initial-state fidelity and the generic engine safety gates passed;
- 1,805,576 events validated with zero errors and zero warnings.

The raw 4.1 GiB corpus is retained outside Git at
`/data/freeciv/gdo5-combat-material-atomic-repair-pilot-v1`. The self-hashed
audit is
`benchmarks/gdo/gdo5_combat_material_atomic_repair_engine_pilot.json`, report
hash
`db748b269690276cc9b5a3f506abe6281a84c42a2da4c17c2b2a2a5a8f95dc65`.
The hash was independently recomputed from the canonical report with its
`report_hash` member omitted.

| Metric | B1 baseline | Material authority | Delta |
| --- | ---: | ---: | ---: |
| Selected operations | 119 | 103 | — |
| Activated operations | 46 | 80 | — |
| Activation / selection | 38.66% | 77.67% | +39.01 pp |
| Completion / selection | 70.59% | 78.64% | +8.05 pp |
| Adverse terminal / selection | 29.41% | 21.36% | −8.05 pp |
| Completion / activation | 97.83% | 98.75% | +0.92 pp |
| Partial activations | 0 | 0 | pass |
| Hard-current reservation conflicts | 0 | 0 | pass |
| Selected-target conflicts | 0 | 0 | pass |
| Non-positive material activations | 0 | 0 | pass |

All 80 treatment authority rows were the predeclared
`attack_then_conditional_attack` operation and `unit_attack` action type.
Treatment authority was true for all 80; the 46 baseline observations retained
false authority. The captured replay continued to establish lower duplicate
targeting than B1.

The treatment positive-sample scheduler p95 was `10.16 ms`, below the
predeclared `50 ms` ceiling. Every immediate terminal-loss observation was
uncensored. The treatment-minus-baseline expected-versus-realized residual
shift was `-0.8874` shield-equivalent points per committed step, favorable and
inside the maximum adverse shift of `+1.0`.

Every conjunctive GDO-5 gate passed. This closes the bounded live pilot gate
for the declared attack operation and satisfies the program requirement for
one additional operation slice beyond city defence. It does not generalize
authority to the other operation types listed in the plan.

## Gameplay outcome boundary: failed first pilot

The pilot was designed and labeled for mechanism evidence, not a gameplay
claim. Its score result was unfavorable:

- paired score delta: −2.67;
- paired 95% interval: `[-5.73, +0.13]`;
- exact two-sided paired randomization p-value: `0.0917`;
- fixed-horizon lead-rate delta: −3.33 percentage points.

The mechanism made selected combat operations much more likely to execute and
finish, but that did not translate into score. This is evidence that
operation completion alone is not a sufficient utility target. The grounded
plan must retain the corrected atomicity boundary while continuing to
calibrate when combat authority is strategically preferable to B1.

## Gameplay outcome boundary: passing fresh pilot

The fresh pilot also remained ineligible for a score or win-rate claim by
design. Its descriptive paired outcome was:

- paired score delta: `+2.37`;
- paired 95% interval: `[-0.83, +5.80]`;
- exact two-sided paired randomization p-value: `0.1876`;
- fixed-horizon lead-rate delta: `-6.67` percentage points, with interval
  `[-20.00, +6.67]`;
- treatment-only versus baseline-only leads: `1` versus `3`.

The score direction is encouraging but statistically unresolved and is not
consistent with the lead-rate direction. The defensible conclusion is narrow:
the atomic repair corrected the observed lifecycle defect, and bounded material
authority causally improved the predeclared operation mechanism without
violating its safety or latency gates. A future score claim would require a
separately predeclared, score-eligible confirmation cohort; these pilot seeds
must not be reused for tuning or confirmation.
