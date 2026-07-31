# GDO-5 material-aware combat engine diagnostic

Date: 2026-07-31

Branch: `experimental/pln-pressure–bridge–fluid`

Authority: bounded combat-operation authority in the treatment arm only

Claim status: diagnostic mechanism evidence; no score or win-rate claim

## Why this cohort was necessary

The retained probability-only combat diagnostic improved operation lifecycle
completion but did not improve score. Inspection of Freeciv's native action
subsystem established that an `ACTRES_ATTACK` probability interval is a real
attacker-win interval, not merely an action-availability score. The defect was
therefore downstream: the operation readout maximized win probability without
accounting for the units being exchanged.

The corrected readout binds the native attacker-win interval to exact ruleset
build costs and current hit points. Its conservative bid is the lower bound of
the terminal-destruction-only material advantage:

```text
p_lower * defender_remaining_value
    - (1 - p_lower) * attacker_remaining_value
```

Survivor damage is explicitly unmodeled. A non-positive lower bound abstains.
The estimator is re-run at the current authoritative snapshot before an
operation step can receive authority.

## Frozen engine design

The retained diagnostic is
`combat_operation_material_authority_scenario_diagnostic_v1` in
`profile/freeciv_harness.yaml`.

- 10 paired, disjoint seeds from the predeclared 6.2M seed range;
- 160-turn horizon;
- `civ2civ3` ruleset;
- symmetric high-contact start:
  `csxxxxxxxxxxxxdddddd`;
- three controller workers;
- clean source required;
- baseline and treatment differ only in
  `pressure_combat_operation_authority_enabled`;
- source commit
  `3fbe0a64b7876f747c4148cf2cd45eab2efb763a`;
- 20/20 arms and 10/10 pairs completed;
- zero game or infrastructure failures;
- paired initial-state fidelity and all generic safety gates passed.

The raw aggregate is retained outside Git at
`/data/freeciv/gdo5-combat-material-authority-scenario-diagnostic-v1`.
The self-hashed repository audit is
`benchmarks/gdo/gdo5_combat_material_engine_diagnostic.json`, report hash
`44ae316fbfef1ae0284ce170ad0f59ff2a3e6aff9c055eff743d9a35e72d1055`.
It validates 549,770 events with zero schema errors and zero warnings.

## Mechanism result

| Metric | B1 baseline | Material authority | Delta |
| --- | ---: | ---: | ---: |
| Selected operations | 32 | 24 | — |
| Activated operations | 16 | 22 | — |
| Activation / selection | 50.0% | 91.7% | +41.7 pp |
| Completed selected operations | 28 | 22 | — |
| Completion / selection | 87.5% | 91.7% | +4.17 pp |
| Adverse terminal / selection | 12.5% | 8.33% | −4.17 pp |
| Completed activated operations | 16 / 16 | 22 / 22 | both 100% |
| Partial activations | 0 | 0 | 0 |
| Hard-current reservation conflicts | 0 | 0 | 0 |
| Selected target conflicts | 0 | 0 | 0 |
| Non-positive material activations | 0 | 0 | 0 |

All 22 treatment authority rows were
`attack_then_conditional_attack` operations issuing `unit_attack`; no other
operation or action type received this authority.

Captured replay independently establishes the duplicated-targeting comparison:
atomic scheduling has zero duplicated targets while the frozen independent B1
readout has five across five captured decisions. The engine cohort confirms
that the scheduled operation set itself has no selected-target conflict.

## Expected-versus-realized friendly loss

The audit uses the same boundary as the estimator:
terminal destruction of the current attacker only. For each committed step it
links the operation action ID and actor identity to the first authoritative
same-turn snapshot after commit. A missing actor realizes its current
shield-equivalent remaining value; a present actor realizes zero terminal
loss. Damage to a survivor is not silently counted because the estimator does
not model it.

| Metric | B1 baseline | Material authority |
| --- | ---: | ---: |
| Resolved committed steps | 16 | 22 |
| Censored steps | 0 | 0 |
| Expected friendly terminal loss, upper mean | 1.84125 | 2.21750 |
| Realized immediate terminal loss, mean | 0 | 0 |
| Realized minus expected-upper residual | −1.84125 | −2.21750 |

The treatment residual shift is −0.37625 shield-equivalent points per
committed step, so the observed direction is safer, not adverse.

This diagnostic cannot formally pass the plan's *predeclared tolerance* gate:
the plan declared the metric but not a numeric tolerance before these seeds
were run. The repository does not retrofit a threshold after seeing the
outcomes.

## Timing

Most snapshots have no supported combat operation and correctly record zero
scheduler time. On positive scheduler samples:

| Arm | Samples | p95 | Maximum |
| --- | ---: | ---: | ---: |
| B1 baseline | 50 | 25.33 ms | 34.03 ms |
| Material authority | 37 | 22.39 ms | 24.30 ms |

The positive-sample treatment p95 is below the 50 ms bound and below baseline.

## Gameplay outcome boundary

The paired score estimate is directionally positive but inconclusive:

- score delta: +2.9, paired 95% interval `[-1.9, +9.9]`;
- score-margin delta: +10.2, paired 95% interval `[-4.6, +28.4]`;
- exact paired score randomization p-value: 0.5625;
- fixed-horizon lead-rate delta: 0.

The cohort was predeclared claim-ineligible and has only ten pairs. These
numbers are diagnostic context, not evidence of a score or win-rate
improvement.

## Fresh pilot predeclaration

The next cohort,
`combat_operation_material_authority_pilot_v1`, is frozen before execution:

- 30 paired seeds in the disjoint 6.3M range;
- the same isolated policy comparison and 160-turn scenario;
- only `attack_then_conditional_attack` may receive authority;
- friendly loss is measured as shield-equivalent terminal destruction per
  committed step;
- the observation is the first authoritative same-turn snapshot after commit;
- absence of such a snapshot is censored, never imputed;
- the maximum allowed adverse treatment-minus-baseline calibration-residual
  shift is **1.0 shield-equivalent point per committed step**.

One point is 10% of the cheapest supported attacker's build cost in this
ruleset. The profile validator rejects malformed or missing predeclarations.
The fresh pilot passes only if every executable GDO-5 gate passes; it remains
ineligible for a score claim regardless of its gameplay outcome.
