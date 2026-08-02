# FDAS engine-live shadow smoke

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Claim scope: one-seed engine integration and observability only

Historical checkpoint: this smoke remains valid at its stated scope but is
superseded for current empirical disposition by
`fdas-engine-shadow-cohort.md`.

## Configuration

- Harness: `profile/freeciv_harness.yaml`
- FDAS profile: `profile/dependent_atomspace_shadow_sampled.yaml`
- Condition: `e_full_loop`
- Predeclared seed: `104729`
- Horizon: 30 turns
- Ruleset: Civ2Civ3
- FDAS policy authority: disabled in both declaration and capability manifest
- Cold verification: deterministic 5% sampling

The first attempt exposed an `int(None)` defect when a protected legacy
`production_defense` candidate was read as though it were a unit-removal
operation. The harness now retains a bounded traceback for infrastructure
failures, and the candidate factory keeps production-defense control routes
separate from unit-removal checks. The identical seed then completed.

## Completed-run evidence

| Measurement | Result |
|---|---:|
| Horizon reached | yes, observed turn 30 |
| Rich revisions committed | 52 |
| Shadow decisions / pressure graphs | 51 / 51 |
| FDAS projection latency p50 / p95 / max | 72.24 / 86.35 / 204.30 ms |
| FDAS shadow readout p50 / p95 / max | 1.52 / 2.08 / 4.56 ms |
| Maximum atoms / scopes / supports | 609 / 10 / 424 |
| FDAS authority actions | 0 |
| Illegal FDAS bindings | 0 |
| Authority violations | 0 |
| Safety downgrades | 0 |
| Candidate/event detail omissions | 0 / 0 |
| Event-schema validation | passed, 29,031 events |

The engine status recorded 52 engine actions, 22 meaningful actions, 21 legacy
impact actions, zero rejected actions, and zero operation-authority actions.
All 51 `atomspace_shadow_decision` events state `authority_eligible: false`.
The run manifest binds the enabled sampled profile while retaining
`authority_enabled: false` and `policy_authority: false`.

## Interpretation and non-claims

This proves that the rich projection, local goal/candidate readout, PF-v2
adapter, causal event stream, and existing controller can coexist for one live
30-turn game without giving FDAS action authority. It also confirms that the
live state distribution is substantially cheaper than the worst frozen
captures in this smoke.

It does not prove score or win-rate improvement, selection parity across a
cohort, bounded authority safety, or long-horizon stability. The run lost and
was not designed as an outcome comparison. At this checkpoint, manifest
promotion beyond `component-only` remained blocked on broader engine evidence
and on closing the remaining explained candidate/latency gaps in captured
replay; the later paired cohort closes the declared component-level engine
gate without promoting authority.
