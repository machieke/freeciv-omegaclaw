# Phase 8 / M4 evidence

Date: 2026-07-18 UTC

## Implementation

The belief layer stores immutable observations and uncertain beliefs separately from
transactional own-state atoms. Revisions carry provenance sets and formulas; the
store applies each `(atom, provenance)` once, even when three derivation paths
converge. Decay, abduction, uncertain deduction, and induction parameters are all in
`profile/freeciv_agent.yaml` and its published schema. Opponent memory is scoped by
opponent, ruleset, and model and reads prior games before current post-game truth is
recorded. Omniscient data is accepted only by the post-game calibration boundary.

## Acceptance results

- P8.A1: the deterministic 50-fixed-opponent calibration audit reports every
  populated 0.1 bucket as within +/-0.15 or explicitly insufficient-sample, with
  pooled and opponent counts. Release-engine aggregation applies the same code to
  packet-visible observations.
- P8.A2: replaying the same observation stream twice produces byte-identical beliefs.
- P8.A3: one provenance reaching a conclusion through three paths contributes once.
- P8.A4: the post-game audit exceeds 80% truth for confidence over 0.5 and confirms
  that every inferred enemy claim remains uncertain.
- P8.A5: the configured linear window crosses the action threshold and returns a
  re-scout decision rather than an action based on stale belief.
- P8.A6: the full M1 native parity suite remains zero-mismatch with beliefs installed.
- P8.A7: schema/config/static release audits account for all observation, abduction,
  induction, dampening, decay, and threshold values and their sweep axes.

## Repeatable command

```bash
pytest -q Autotests/test_freeciv_beliefs.py Autotests/test_freeciv_oracle.py
```

Result: all belief and crisp-oracle regressions passed.
