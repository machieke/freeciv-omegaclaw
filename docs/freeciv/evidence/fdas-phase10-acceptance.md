# FDAS Phase 10 aggregate acceptance report

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`  
Acceptance level: component-only; default runtime and policy authority disabled

## Consolidation realized

- `planning/impact.py` is now a 75-line compatibility facade. Stable contracts,
  pure helpers, and explicit strategic defaults live in `impact_types.py`; the
  unchanged imperative implementation remains isolated in `impact_legacy.py`.
- `state/atoms.py` remains an 87-line compatibility facade over the typed FDAS
  builder, while retaining the frozen historical projector for rollback.
- A versioned replacement inventory maps every retained Impact/atom branch to
  exact capabilities, tests, policy defaults, and rollback identities.
- Legacy removal fails closed unless all replacement capabilities are
  `engine-live`, every named replacement test is verified, and the rollback
  identity remains available. No current branch qualifies, so none was removed.
- `SnapshotStore(atomspace_mode="legacy")` is a tested revision-free rollback
  path producing the byte-identical historical atom view. The default remains
  `dependent`.
- Focused scope activation records reason, funding source, causal parents,
  priority, TTL momentum, and explicit budget rejection. The projector wrapper
  publishes only funded detail scopes and cannot omit world/empire scopes.
- Read-only operator diagnostics cover statistics, scopes, explain, why-not,
  diff, dependencies, dependents, shadow decisions, and cold verification.
- The published event schema and generated TypeScript include the bounded FDAS
  causal vocabulary. Revision emission is causal, revision-bound,
  structurally hashed, and explicitly capped.
- Authority validation now requires aggregate and per-capability promotion,
  exact domain projections, explanations, learning holdouts, research parity,
  and nonzero cold verification before engine-live acceptance.

## Exit-criterion disposition

| Criterion | Result |
|---|---|
| No removed behavior lacks a replacement test | Passed vacuously and enforced prospectively: no semantic branch was removed |
| Live profiles declare exact slices | Passed for checked state: default flags are off and manifest is `component-only`; no live claim is made |
| Rollback remains available | Passed with explicit `legacy` SnapshotStore mode and versioned rollback profile |
| Cold/incremental, safety, replay, and latency gates | Passed at component, captured-replay, and paired three-seed engine-shadow scope; authority promotion remains unclaimed |
| Compatibility files are integration facades | `planning/impact.py`: 75 lines; `state/atoms.py`: 87 lines |

## Verification

- Focused FDAS surface: `195 passed in 38.32s`.
- Harness integration surface: `106 passed in 296.38s`.
- Complete FreeCiv acceptance suite: `1,292 passed in 380.72s`.
- Captured rich replay: 38 replayable snapshots, 37/37 transition
  cold-equivalence checks, zero runtime failures, zero binding/authority/safety
  violations.
- Engine-live paired rich shadow: three predeclared 30-turn seeds completed
  with exact 188-action/result parity, 90 shadow decisions, five equivalent
  cold proofs, zero FDAS authority actions, 147.31 ms FDAS p95, and 444.41 ms
  controller p95.
- Generated event types: current.
- Frozen Phase 0 semantic baseline: reproduced as
  `beb5c88ecd312784da3129ade47c3dc948203d18bc05cf61299a2b5a23b08e07`.
- `git diff --check`: clean at each committed slice.

The unscoped `pytest -q Autotests` command is not a valid monolithic harness:
nested Slack and Telegram mock suites require isolated import paths, and the
top-level non-FreeCiv suite invokes external Docker/plugin fixtures. The
complete `Autotests/test_freeciv_*.py` suite is the repository-wide acceptance
surface used here.

## Non-claims

This report does not promote any capability to `shadow-live`,
`bounded-authority`, or `engine-live`. It does not claim score or win-rate
improvement. The captured corpus has nine old fixtures that cannot be strictly
replayed, and the three live games are integration/parity evidence rather than
an outcome cohort. The strict manifest prevents those limitations from
escaping into policy authority.
