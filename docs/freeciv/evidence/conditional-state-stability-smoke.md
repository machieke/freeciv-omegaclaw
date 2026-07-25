# Conditional authoritative-state stability smoke

Date: 2026-07-25

Status: focused contract tests, a two-seed profiling control, two independent
two-seed engine treatments, and a four-trace release audit passed. This is
correctness and engineering-latency evidence, not a gameplay score or win-rate
claim.

## Profile-guided target

New turn-boundary diagnostics split the time before each scheduler decision
into the authoritative state gate, state-query round trips, DTO parsing,
required stability wait, residual bookkeeping, and event checkpoint sync.
The control at
`artifacts/freeciv/turn-boundary-profile-20260725` measured:

| Boundary component | Two-seed mean |
|---|---:|
| Complete boundary | 236.0 ms |
| Authoritative state gate | 227.8 ms |
| Two state-query round trips | 163.6 ms |
| Required quiet interval | 50.0 ms |
| DTO parsing | 11.5 ms |
| Non-state bookkeeping | 8.2 ms |
| Turn checkpoint sync | 3.8 ms |

The state gate accounted for 96.5% of the boundary. Server turn advancement
and the 50 ms quiet interval are correctness requirements. The avoidable work
was rebuilding, serializing, transmitting, and parsing the complete
authoritative projection for the second identical sample.

## v4 conditional stability protocol

The v4 proxy contract adds `accept_unchanged` to a bounded
`pln_authoritative` source wait. After the complete wait expires without a new
fully stored packet revision, the proxy can return a compact
`state_unchanged` acknowledgment containing the exact turn and source
sequence. If a packet arrives, it returns the ordinary full state and the
harness restarts fingerprint stability.

This does not weaken the two-sample gate:

- packet mutation and authoritative projection construction share one
  reentrant CivCom lock, so the retained full projection cannot mix revisions;
- the unchanged check uses that same lock;
- the full 50 ms independent wait remains;
- the harness accepts the acknowledgment only for its retained projection's
  exact turn and source sequence;
- any changed revision still receives full state, DTO parsing, and complete
  decision-fingerprint comparison.

Legacy state queries and v3 bounded waits retain their existing semantics.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn engine topology,
the resident `qwen3-coder-next:latest` model, and identical planner, score,
observer, and durability configuration:

- full-sample control:
  `artifacts/freeciv/turn-boundary-profile-20260725`
- conditional treatment:
  `artifacts/freeciv/conditional-stability-treatment-20260725`
- independent treatment repeat:
  `artifacts/freeciv/conditional-stability-treatment-repeat-20260725`

| Measure (two-seed mean) | Control | Treatment | Repeat |
|---|---:|---:|---:|
| Boundary state gate | 227.8 ms | 204.1 ms (-10.40%) | 204.9 ms (-10.07%) |
| Complete boundary | 236.0 ms | 215.6 ms (-8.64%) | 216.3 ms (-8.34%) |
| DTO parsing | 11.5 ms | 6.4 ms (-44.40%) | 6.0 ms (-48.36%) |
| Mean turn loop | 528.7 ms | 495.7 ms (-6.24%) | 496.6 ms (-6.08%) |
| Gameplay | 20,010.2 ms | 19,279.5 ms (-3.65%) | 18,789.4 ms (-6.10%) |
| Complete backend | 21,695.1 ms | 20,977.1 ms (-3.31%) | 20,522.8 ms (-5.40%) |

The required stability wait remained exactly 50.0 ms in every cohort.

## Behavioral acceptance

Control, treatment, and repeat retained, per seed:

- identical initial authoritative fingerprints;
- bit-for-bit canonical action hashes:
  - 104729:
    `3e5da136c5f69d7c700ad80c794c87c0da9a44205dd317c675a7e7d3a874dcf5`;
  - 104743:
    `6c66824aeb87a6ee98be7707da0c53316c279b44def2cae6c9fbbb4eba1de376`;
- scores and margins 107/-2 and 112/-3;
- 48/70 engine actions, 18/40 planned actions, and 17/39 impact actions;
- one/two settlement completions;
- zero rejected actions and zero deferred, expired, pending, or timed-out
  confirmations.

## Verification

- Focused host state/turn-cycle lane: 13 passed.
- Complete repository FreeCiv lane: 343 passed.
- Focused patched-proxy lane: 116 passed, 4 skipped.
- Publite2 regression lane: 2 passed.
- Engine comparison: 6/6 games completed without infrastructure failures.
- Four treatment traces passed every release-audit check, including the pinned
  external contract and PF-PLN phase audit.
