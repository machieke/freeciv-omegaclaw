# PR94 retained-capacity episode dataset audit

## Result

The immutable 16-game PR92 diagnostic cohort exports losslessly into a
deterministic offline PR93 episode dataset. All eight mechanical gates pass,
all 16 games remain represented, all seven terminal labels recompute through
the production episode bridge, and there are no extraction errors or identity
collisions.

The frozen evidence-adequacy decision is `insufficient-evidence`. This is the
scientifically important result: the available observations are suitable for
testing episode mechanics, but not for fitting or confirming a calibrated
transition-value model.

## Dataset

- Fixed games: 16
- Games with at least one episode: 4
- Terminal episodes: 7
- `no-effect-observed`: 4
- `effect-without-goal-relief`: 1
- `goal-relief-observed`: 2
- Extraction errors: 0
- Source commit: `db96e2045a118d13747ca8da199f88cf1c5cf2f2`
- Parent cohort hash:
  `e061c529bb31153316ab7947810ae3e35f25c4fa76a04e49dd411e8cb008528f`

Each dataset row includes the typed episode plus exact game, seed, proposal
event, terminal label, and parent-audit identity. The exporter reparses the
serialized episode and requires proposal, RequirementSet, resource claim,
deficit atom, before/after revision, and terminal-label provenance. Prediction
IDs remain empty and execution IDs remain absent.

## Descriptive uncertainty

The frozen 95% Wilson intervals are deliberately reported to make the sparse
evidence visible:

| Fixed-cohort quantity | Estimate | 95% Wilson interval | N |
|---|---:|---:|---:|
| Games with an episode | 25.0% | 10.2% to 49.5% | 16 |
| Exact-product effect per episode | 42.9% | 15.8% to 75.0% | 7 |
| Durable goal relief per episode | 28.6% | 8.2% to 64.1% | 7 |

These intervals describe a reused, yield-selected diagnostic seed set. They
are not general population estimates and do not establish causation.

## Adequacy gate

The preregistered minima and observed counts are:

| Requirement | Required | Observed | Pass |
|---|---:|---:|---:|
| Terminal episodes | 30 | 7 | No |
| Independent games with episodes | 20 | 4 | No |
| `no-effect-observed` | 10 | 4 | No |
| `effect-without-goal-relief` | 10 | 1 | No |
| `goal-relief-observed` | 10 | 2 | No |
| Exact complete provenance | required | complete | Yes |
| Disjoint discovery and confirmation cohorts | required | absent | No |

No model is fitted, no retrospective threshold is relaxed, and no episode is
connected to conductance, induction, or candidate readout.

## Determinism and validation

The full 16-game export was performed twice. Both outputs were byte-identical:

- Dataset structural hash:
  `bb9971c39a114a035bbc3894a29b939b642ea7e1f25fbe955dec4a05f226824e`
- File SHA-256:
  `01648060120ad8bbbc0f28d0e74338c7a403c7cd4e4ced90474d0739f25878ba`

The focused exporter and episode-audit suite passed 43 tests. Dedicated tests
reject duplicate seeds, duplicate operation labels, source mismatch, missing
proposal evidence, nonterminal labels, store tampering, and parent-audit
failure.

The machine-readable dataset and audit report is
`docs/freeciv/evidence/fdas-pr94-retained-capacity-episode-dataset.json`.

## Next bounded target

Do not train on these seven rows. The next step is to define a proposal-time,
non-authorizing feature and prediction schema, then preregister independent
discovery and confirmation cohorts sized for the rarest observed status. New
predictions must be frozen before terminal outcomes and retain confidence
intervals; only held-out calibration evidence can justify a later readout
experiment.
