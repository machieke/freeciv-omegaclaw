# Packet-sequence-aware extractor cache smoke

Date: 2026-07-25

Status: correctness fix, focused regression, full host suite, two-seed engine
acceptance, and exact repeat acceptance passed. The timing and score results are
diagnostic engineering evidence, not a population-wide performance or score
claim.

## Root cause

The proxy had two state caches. The outer WebSocket response cache was keyed by
game, player, format, turn, and packet `source_seq`, but the inner
`StateExtractor` cache was keyed only by game, player, format, and turn.

FreeCiv acknowledged the turn-1 research action and delivered
`PACKET_RESEARCH_INFO` in approximately one millisecond. The outer query then
missed correctly at the new packet sequence, but the extractor returned its
pre-action turn-1 payload until the configured five-second TTL expired. The
same defect hid same-turn unit and city effects, causing otherwise successful
impact actions to consume their 300 ms confirmation deadline and enter the
deferred ledger.

The correction adds the current `source_seq` to the extractor cache identity.
A focused regression mutates research at the same turn and proves the next
packet revision cannot reuse the prior formatted payload. The tracked proxy
patch digest is
`bbddbb12b18cb53079f624779cbceff810e94b88a13eac544316c8d453e4118f`.

## Engine cohorts

All cohorts used the same seeds, serial topology, 30-turn horizon, model,
planner policy, and active-listener server recycle:

- turn-only extractor control:
  `artifacts/freeciv/active-listener-recycle-smoke-20260725`
- packet-sequence treatment:
  `artifacts/freeciv/extractor-source-seq-cache-smoke-20260725`
- independent packet-sequence repeat:
  `artifacts/freeciv/extractor-source-seq-cache-repeat-20260725`

| Measure (two-seed mean) | Control | Treatment | Repeat | Control to treatment |
|---|---:|---:|---:|---:|
| Gameplay | 34,407.5 ms | 24,623.5 ms | 24,601.2 ms | -9,784.1 ms (-28.44%) |
| Complete backend | 40,838.5 ms | 30,596.3 ms | 31,139.9 ms | -10,242.2 ms (-25.08%) |
| Mean turn loop | 993.3 ms | 670.3 ms | 665.8 ms | -323.0 ms (-32.52%) |
| Impact confirmation | 268.3 ms | 128.6 ms | 129.4 ms | -139.7 ms (-52.06%) |
| Confirmation timeouts | 55 | 0 | 0 | -55 |

The first treatment's mean gameplay differed from the repeat by only 22.3 ms
(0.09%). Seed 104729 includes the first process-local model call in both
treatment runs; seed 104743 reuses the deterministic model-selection cache.

## Correctness and behavior

The stale-cache control is not a behavioral reference: it withheld
authoritative same-turn effects from the planner. Correct visibility therefore
changes grounded action selection legitimately.

| Seed | Control score / margin | Treatment score / margin | Control actions | Treatment actions | Control / treatment settlements |
|---:|---:|---:|---:|---:|---:|
| 104729 | 107 / -2 | 107 / -2 | 71 | 48 | 1 / 1 |
| 104743 | 109 / -6 | 112 / -3 | 68 | 70 | 1 / 2 |

For each seed, the first treatment and independent repeat had identical:

- initial state fingerprint and initial legal-action-family fingerprints;
- canonical action sequence (bit-for-bit);
- engine and meaningful-action counts;
- fixed-horizon score and margin;
- city and settlement outcomes;
- zero rejected actions;
- zero deferred, expired, or pending confirmations.

Both treatment cohorts reached turn 30 with no infrastructure failures. All
four cognitive traces passed the full release audit.

## Verification

- Focused patched-proxy suite: 113 passed, 4 skipped.
- Full repository FreeCiv suite: 335 passed.
- Fresh patch reverse-check: passed against pinned upstream commit
  `26ba7124249f34fd3050ef29bf191bd4d8808018`.
- Full release audit: all checks passed, including the pinned external
  contract and all four engine traces.

## Scope

This establishes a same-turn state-correctness defect and validates its fix on
two deterministic engine seeds with an independent repeat. The observed
latency reduction is consistent with removing the five-second inner cache TTL
and 55 false confirmation timeouts. The non-regressing diagnostic scores do not
establish a general score or win-rate effect; a fresh powered cohort would be
required for that claim.
