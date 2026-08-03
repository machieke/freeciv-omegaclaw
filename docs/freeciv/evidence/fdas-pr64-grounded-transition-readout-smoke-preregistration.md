# FDAS PR64 grounded-transition readout smoke preregistration

Date: 2026-08-03

## Question and boundary

PR63 permits a separate default-off shadow readout-yield experiment with the
confirmed PR60 grounded-transition model. PR64 asks whether that exact model
can be loaded through a hash-bound manifest, expose candidate-specific
predictions on a fresh engine game, enlarge only a protected candidate union,
and feed the existing decision-safe readout without changing an action.

This is an engineering and readout-yield smoke. It does not observe outcomes
for unselected alternatives and therefore cannot establish ranking quality,
counterfactual value, gameplay impact, score, or win rate.

## Frozen implementation

The activating manifest is
`profile/fdas_manifest_defense_grounded_transition_readout_shadow.json`. It
binds:

- PR60 discovery artifact hash
  `b954be880a28cdd1cbc505b6d3c9a34d0151a424ef7330f31f3d5759f72c45d0`;
- model result hash
  `edca977ffc87f9e731e00d5b5bacf3be03e1d5f28887e51e86966cb975ee3aa5`;
- PR63 confirmation report hash
  `eb15aabe1d2e11eac71f4aaf31939854798445a50fbc76c1e7df32c35326ae42`;
- scalar top-k `1`, at most one calibrated candidate per action category,
  and maximum interval width `0.55`; and
- false action-selection, policy, readout, truth, flow, and capacity-solver
  authority.

The model may estimate only completely grounded reinforcement moves. It must
abstain on fortification and missing or unsupported transition strata.
Candidate-specific levels are `eta`, `route`, `compact`, or `full`, optionally
conditioned on lifecycle. `action` and `lifecycle` are recorded separately as
broad backoff. Calibrated values form the protected candidate union only; the
original scalar score remains authoritative.

The decision-safe readout remains unchanged. A diagnostic preference requires
strict interval separation and exact grounded non-inferiority. Interval overlap
is an explicit, acceptable abstention and never a reason to loosen the frozen
gate.

## Fresh execution and acceptance

The single fixed execution seed is `109007`, which is outside PR59 through
PR63. The profile declares a schema-valid 30-seed fresh pool, while
`--limit-seeds 1` fixes execution to its first seed. The smoke uses the exact
160-turn profile and one clean source commit:

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr64-grounded-transition-readout-smoke-v1 \
  --config profile/freeciv_harness_fdas_pr64_grounded_transition_readout_160_turn.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_grounded_transition_candidate_readout.py \
  artifacts/freeciv/fdas-pr64-grounded-transition-readout-smoke-v1 \
  --expected-seed 109007 \
  --expected-source-commit "$SOURCE_COMMIT" \
  --output docs/freeciv/evidence/fdas-pr64-grounded-transition-readout-smoke.json
```

The audit passes only if:

- the fixed seed reaches the horizon or a genuine absorbing terminal without
  infrastructure failure or rejected actions;
- the event ledger is valid and warning-free, and the exact clean source,
  config, and manifest are recorded;
- candidate-choice, grounded-transition union, and decision-safe event counts
  agree with all status counters;
- every event is revision-bound, hash-valid, and denies undeclared authority;
- the exact PR60/PR63/model hashes and grounded-transition model kind are
  present on every union event;
- at least one prediction is estimated and at least one is from a
  candidate-specific transition level; and
- every decision-safe preference or abstention satisfies the existing strict
  interval and grounded-mechanics contract.

An actual preference, calibrated addition beyond scalar top-1, or interval-
overlap event is not required in a one-game mechanics smoke. Their counts must
be reported honestly if they occur.

## Stop rules

- Preserve a failed run or audit as failed evidence.
- Do not replace, retry, add, or remove the fixed seed after collection starts.
- Do not change model, thresholds, manifest, audit, or endpoint semantics after
  execution starts.
- Do not grant the shadow readout action authority regardless of smoke result.
- A pass permits a separately preregistered fresh yield cohort only; it does
  not permit a ranking, outcome, gameplay, score, or win-rate claim.
