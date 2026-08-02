# FDAS PR 16: expansion lifecycle shadow activation

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Status: declared `shadow-live`; policy authority disabled
Machine-readable engine evidence: `fdas-pr16-expansion-shadow-engine.json`

## Acceptance boundary

This increment promotes only the expansion lifecycle slice of PR 16 from its
Phase 7 component boundary into engine-live shadow execution. It does not add
an expansion policy or replace the existing Impact controller. The legacy
controller still selects and sends every action.

The live seam consists of:

- `profile/dependent_atomspace_expansion_shadow.yaml`, enabling city, unit,
  region, native route-corridor, settlement-site, population-recovery, and
  durable operation projection while leaving every authority flag false;
- `profile/fdas_manifest_expansion_shadow.json`, declaring only the exercised
  expansion capabilities `shadow-live`;
- a durable `fdas-expansion-operations.json` store with identity, digest, and
  quarantine checks;
- exact same-snapshot bindings for advertised `unit_build_city` and
  `unit_join_city` actions;
- explicit `RequirementSet` and actor/resource claims attached to current
  bindings;
- causal `operation_activated`, `operation_completed`, `operation_failed`,
  and `operation_expired` events that all retain `policy_authority: false`,
  `shadow_only: true`, and `selected: false`;
- a deterministic engine-run auditor that validates store integrity, action
  and effect causality, terminal telemetry, cold equivalence, latency, and the
  complete absence of FDAS authority.

Server acceptance is not treated as the operation effect. An accepted founder
action moves the operation into the active/awaiting-effect state. Completion
requires a later authoritative snapshot in which the founder is consumed and
the required city or population effect exists. Founder loss without that
effect is a failure. A deadline reached without an attempt is an expiration,
not a failed transition estimate.

## Scoped refresh policy

The first diagnostic used a rich FDAS refresh after every accepted action. It
was correct but unnecessarily expensive: one turn can contain several actions
that cannot affect the expansion lifecycle. The accepted implementation now
uses `turn-boundary-before-readout` plus one exact action-scoped refresh when
the legacy controller is about to execute `unit_build_city` or
`unit_join_city` and the current rich revision is stale.

This retains the consequential same-snapshot binding while avoiding rich
projection after unrelated production, movement, and end-turn actions. The
effect is reconciled at the next bounded rich observation. No stale binding is
allowed to match, and an ambiguous match fails closed.

## Fresh engine confirmation

The implementation and auditor were committed before execution. The clean
cohort used pinned seed `104729` and source commit
`1345eb81f5d5dbd930d97fd6833638c2d69c0278`:

```bash
FREECIV_RULESET_ROOT=/path/to/freeciv/data \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_expansion_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_expansion_shadow.json \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-expansion-shadow-live-30-v2 \
  --config profile/freeciv_harness.yaml \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

python3 scripts/freeciv/audit_fdas_expansion_live.py \
  --game-dir artifacts/freeciv/fdas-expansion-shadow-live-30-v2/games/main/e_full_loop/104729-00 \
  --output docs/freeciv/evidence/fdas-pr16-expansion-shadow-engine.json
```

Results:

| Measure | Result |
|---|---:|
| Audit gates | 15 / 15 |
| Engine actions / accepted results / rejects | 52 / 52 / 0 |
| Shadow readouts: complete / not applicable | 16 / 14 |
| Missing legacy / extra FDAS candidates | 0 / 0 |
| Authority events / actions | 0 / 0 |
| Durable operations / projected operations | 2 / 2 |
| Exact expansion action matches | 1 |
| Authoritative effect completions | 1 |
| Unattempted expirations / failed effects | 1 / 0 |
| Sampled cold verifications / failures | 1 / 0 |
| FDAS projection p50 / p95 | 72.30 / 118.39 ms |
| FDAS shadow readout p50 / p95 | 1.98 / 2.59 ms |
| Full-controller p50 / p95 | 28.01 / 490.65 ms |

The completed operation was an exact legacy-selected `unit_build_city` for
founder `102` at tile `484`. Its event graph proves
`action_sent -> action_result -> operation_activated -> authoritative snapshot
-> operation_completed`. The accepted result was not itself used as the
completion witness. The other operation represented a legal population
recovery alternative; it was never selected or attempted and expired after
its declared deadline.

The deterministic audit structural hash is
`08b07102e6984ef2de82ff1d31d16af1622994d7fefc4ce1f0c7c0a06ccb42fe`.
The tracked report file SHA-256 is
`73f0347c5cce92ba4202befb49d566aad498cb61a42a9ad0f01d52136b34461f`.
The source implementation SHA-256 recorded by the run is
`00bb85e234416ca54448638ee5bb96e38f2ed6ba91f61b4e084cb480c2744923`.

## Verification

The focused configuration, runtime, expansion lifecycle, and live-audit suite
passed 62 tests. The complete FDAS suite passed 223 tests before the clean
cohort. The clean audit then independently validated the persisted event and
operation artifacts rather than trusting terminal counters alone.

## Claim boundary and remaining work

This is one pinned-seed mechanism, safety, behavior-preservation, and ordinary
latency confirmation. It is not a score or win-rate experiment. The FDAS
expansion slice did not choose a different action and has no policy authority.

Expansion bounded authority remains a separate future increment requiring a
frozen replay corpus, negative safety cases, exact commit revalidation,
rollback evidence, and a fresh multi-seed confirmation. Transport and combat
remain `component-only` and must proceed as independent projection, shadow,
replay/safety, and authority increments rather than being folded into this
activation.
