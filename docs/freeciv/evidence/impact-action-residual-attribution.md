# Impact-action residual attribution

Date: 2026-07-26

Status: complete two-layer, two-seed engine attribution with exact action
replay. This is diagnostic evidence for optimization selection, not a
gameplay-score, win-rate, or outer latency claim.

## Action residual

The fresh cohort
`artifacts/freeciv/impact-action-residual-attribution-20260726-a` divided the
33.836 ms/turn non-refresh action phase as follows:

| Component | Latency |
|---|---:|
| Impact execution and acknowledgement | 11.417 ms/turn |
| Impact planning | 8.984 ms/turn |
| Confirmation non-state work | 4.510 ms/turn |
| Pressure and plan event emission/registration | 3.286 ms/turn |
| Post-confirmation outcome bookkeeping | 2.845 ms/turn |
| Pre-confirmation bookkeeping | 0.035 ms/turn |
| Remaining loop/timer residual | 2.759 ms/turn |

The 4.510 ms confirmation non-state component contains 2.413 ms/turn of
post-query planner observation/pruning and 1.363 ms/turn of authoritative
state-event emission. The remainder covers refresh wrapper and predicate work.
Authoritative refresh itself remained separately attributed at
88.599 ms/turn and is not included in this residual.

## Execution boundary

The second fresh cohort
`artifacts/freeciv/impact-execution-attribution-20260726-a` divided each
12.386 ms impact execution as follows:

| Component | Latency | Share |
|---|---:|---:|
| Proxy transport and acknowledgement | 10.543 ms | 85.1% |
| Result and plan-step event emission | 1.326 ms | 10.7% |
| Action-sent event emission | 0.415 ms | 3.4% |
| Execution-gate preflight | 0.037 ms | 0.3% |
| Wrapper/timer residual | 0.066 ms | 0.5% |

The proxy acknowledgement is the causal acceptance boundary: proceeding before
it would allow refresh and effect accounting to race an unaccepted action.
It is therefore classified as correctness-bounded rather than an optimization
candidate. The execution gate's exact snapshot, legal digest, canonical-action,
buildability, plan-monitor, and grounded-precondition checks remain intact.

The remaining mutable work is fragmented across required causal events,
planner observation, and outcome bookkeeping. A persistent event descriptor or
file-handle change would need an explicit durability/causal-visibility proof;
the measured upper bound is currently too small to justify that risk.

## Behavioral acceptance

Relative to the preceding pressure-score-reuse cohort, both attribution layers
retained:

- exact ordered canonical action payloads;
- exact run-completion summaries;
- scores and margins 107/-2 and 112/-3;
- zero engine rejections and confirmation timeouts; and
- zero infrastructure failures.

## Verification

- Complete repository FreeCiv lane: 361 passed.
- Focused harness attribution tests: 9 passed.
- Focused async execution-gate diagnostics test: 1 passed.
- Both two-game engine attribution cohorts: 4 completed, 0 infrastructure
  failures.
- All four attribution traces passed all 13 top-level release-audit checks at
  `artifacts/freeciv/impact-action-residual-release-audit-20260726/report.json`.
- Exact ordered-action comparison was empty for both seeds in both cohorts.
- Static compilation and whitespace checks passed.
- The repository-prescribed `just check` entry point remains unavailable because
  `just` is not installed; the complete direct FreeCiv lane above passed.
