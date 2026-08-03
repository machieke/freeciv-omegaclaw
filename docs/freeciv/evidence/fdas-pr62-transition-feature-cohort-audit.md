# FDAS PR62 transition-feature cohort audit hardening

Date: 2026-08-03

## Correction

Feature audit 1.0 mixed two different questions:

1. Is every recorded transition row complete, revision-bound, non-imputed, and
   compatible with the frozen parent model?
2. Did this particular game happen to expose multiple competing moves with
   distinct transition signatures?

The first is a per-game invariant. The second is stochastic opportunity yield
and is meaningful only over the cohort. Requiring the second in every game
made a fortify-only game or a game with sequential single-move decisions fail
despite containing no malformed transition row.

Audit 2.0 preserves the strict per-game requirements:

- the candidate store is valid;
- every present move row carries the complete transition schema;
- no incomplete grounding is accepted or imputed;
- every frozen PR40 prediction is byte-identical;
- fortify rows remain on their frozen schema; and
- all recorded audit errors are absent.

It evaluates opportunity over the complete fixed cohort:

- at least one move row exists;
- at least one multi-move choice set exists;
- at least one multi-move set has distinct transition signatures; and
- at least two grounded signatures exist.

The separate calibration yield evaluator remains stricter and unchanged: it
still requires 12 diverse multi-move sets, 12 observed move outcomes, eight
lineages, six contributing games, outcome contrast, and selected-signature
diversity. Audit 2.0 therefore does not reduce the scientific evidence gate.

## Implementation safety

`audit_fdas_candidate_transition_features_cohort.py` consumes and hash-checks
the complete 1.0 report before reclassifying its already computed row and
cohort measures. It cannot hide a row error, quarantine, incomplete grounding,
changed prediction, or failed parent audit. Its report has a new 2.0 identity
and binds the legacy report hash.

`validate_fdas_candidate_transition_calibration_cohort.py` injects that auditor
into the existing confirmation pipeline. The original validator still defaults
to audit 1.0, so PR60 and PR61 primary artifacts remain reproducible. The v2
confirmation report has a distinct schema identity. Unit tests cover:

- a sparse/fortify-only game accepted inside a competitive cohort;
- rejection of a present but unenriched move row; and
- rejection of a cohort with no multi-move competition.

Ten focused transition calibration/audit tests pass.

## Post-hoc PR61 sensitivity

An exact-source sensitivity rerun over immutable PR61 evidence passes audit
2.0 and all unchanged calibration gates:

- feature-audit hash:
  `076ab0675a6af2d8183bfd079879019b9673bfd56b82d55f5adc2e222fea2213`
- sensitivity report hash:
  `f83a28bcd145913f097cee3bc78a790d9547675edfba2fe4a0588c56adb8a3c8`
- sensitivity JSON SHA-256:
  `c2c2de7ca2cf80f6e0eb9d46bbb09237252f004f8638fc3812a76c072232b103`

This proves the versioned implementation behaves as intended. It does not
replace PR61's failed primary verdict because audit 2.0 was designed after
inspecting that cohort. A fresh, disjoint, preregistered replication is still
required before the model can enter a shadow readout-yield experiment.

Machine-readable diagnostic evidence is in
`fdas-pr61-candidate-transition-calibration-cohort-audit-sensitivity.json`.
