# PLN lazy state-construction smoke

Date: 2026-07-25

Status: focused proxy tests, two independent two-seed engine cohorts, and a
four-trace release audit passed. This is exact-behavior engineering evidence,
not a gameplay score, win-rate, or population-wide latency claim.

## Root cause and change

Every `pln_authoritative` request formerly performed two independent
constructions:

1. `CivCom.get_full_state()` built the generic unit, city, player, and map
   representation;
2. `StateExtractor` built the packet-backed authoritative PLN projection.

The first result was not consumed on a successful authoritative extraction. It
existed only because the shared handler also needs generic state for the
`full`, `delta`, and `llm_optimized` formats and for its manual error fallback.

The handler now loads generic state lazily. Non-PLN formats are unchanged, and
an authoritative extraction failure still loads the generic state exactly once
before invoking the established fallback. Contract tests assert both the
zero-call success path and one-call fallback path.

## Rejected cache alternative

A preceding experiment raised the authoritative extractor cache limit from
4 KiB to 16 KiB so the approximately 4.3 KiB compressed projections could be
reused between identical-sequence stability samples. Cache hits worked, and
the focused suite passed, but authenticated decompression cost approximately
50 ms while rebuilding the projection cost approximately 17 ms. The engine
cohort regressed mean gameplay latency by 1.44%. That experiment and its patch
identity were fully reverted.

## Engine comparison

All runs used seeds 104729 and 104743, a serial 30-turn engine topology, the
resident `qwen3-coder-next:latest` model, two observer-global queries, and the
same planner and durability configuration:

- control:
  `artifacts/freeciv/scheduler-observer-boundary-repeat-20260725`
- treatment:
  `artifacts/freeciv/pln-lazy-state-treatment-20260725`
- independent treatment repeat:
  `artifacts/freeciv/pln-lazy-state-treatment-repeat-20260725`

| Measure (two-seed mean) | Control | Treatment | Repeat |
|---|---:|---:|---:|
| Gameplay | 20,106.2 ms | 19,887.6 ms (-1.09%) | 20,219.6 ms (+0.56%) |
| Complete backend | 21,835.8 ms | 21,583.2 ms (-1.16%) | 21,866.3 ms (+0.14%) |
| Mean turn loop | 534.9 ms | 528.1 ms (-1.28%) | 535.5 ms (+0.10%) |

Pooling the four treatment games gives 20,053.6 ms gameplay (-0.26%),
21,724.7 ms backend (-0.51%), and 531.8 ms mean turn loop (-0.59%) relative to
the two-game control. The opposing repeat results show that the end-to-end
effect is smaller than normal engine variance. Acceptance rests on removing a
provably unused construction with exact behavior, not on claiming a measured
latency improvement.

## Behavioral acceptance

Within each seed, control, treatment, and repeat had identical initial
fingerprints and canonical action hashes:

- 104729:
  `3e5da136c5f69d7c700ad80c794c87c0da9a44205dd317c675a7e7d3a874dcf5`
- 104743:
  `6c66824aeb87a6ee98be7707da0c53316c279b44def2cae6c9fbbb4eba1de376`

Seed 104729 retained score 107, margin -2, 48 engine actions, and one
settlement. Seed 104743 retained score 112, margin -3, 70 engine actions, and
two settlements. Every treatment game had zero rejected actions and zero
deferred, expired, pending, or timed-out confirmations.

## Verification

- Focused patched-proxy lane: 115 passed, 4 skipped.
- Publite2 regression lane: 2 passed.
- Engine treatment: 4/4 games completed without infrastructure failures.
- Four-trace release audit: all checks passed, including the pinned external
  contract and PF-PLN phase audit.
