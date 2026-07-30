# GDO-4 native-route 160-turn confirmation

Status: engine and replay validation passed; GDO-4 policy gate remains closed
Date: 2026-07-30
Branch: `experimental/pln-pressure–bridge–fluid`
Route implementation commits: `bcfd8a6`, `08f0900`

## Purpose

This cohort answers a narrow question: does the new authoritative Freeciv
route boundary survive a real engine run, remain schema-valid and bounded, and
materially improve the grounded city-defence candidate set?

It does. This is mechanism evidence, not a gameplay-score claim. The
city-defence operation path remains shadow-only, the cohort has no paired
no-route policy arm, and two seeds cannot establish a score or win-rate
effect.

## Engine confirmation

The pinned 13-patch upstream series, including
`0013-pln-native-movement-routes.patch`, was applied to the configured Freeciv
checkout. The packet generator, modified server source, and full container
image built and linked successfully. The rebuilt `fciv-net` service reported
healthy during the cohort.

The confirmation command was:

```text
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo4_160_turn.yaml \
  --out artifacts/freeciv/gdo4-native-routes-160-20260730 \
  --backend engine-live --workers 1 --limit-seeds 2 \
  --main-only --condition e_full_loop
```

Both games reached turn 160 without infrastructure failure, event-schema
warning, event-schema error, or rejected engine action:

| Seed | Valid events | Own score | Opponent score | Native routes | Reachable |
|---:|---:|---:|---:|---:|---:|
| 104743 | 6,196 | 127 | 244 | 1,263 | 1,263 |
| 4543804 | 15,398 | 168 | 363 | 9,825 | 9,699 |

The raw event SHA-256 for seed 4543804 is
`722275f2d7fbf683227f37fde6e847c94ea6d0c52d09317d9bd8091d71dfa429`.

## Route-query cost

The harness records route response count and the proxy's route wait separately
from the broader state preparation time. Values below are means per state
request; the interval is the observed two-game range, not a population
confidence interval.

| Phase | Route responses/request | Route wait/request |
|---|---:|---:|
| Turn boundary | 19.34 (5.50--33.19) | 9.26 ms (2.31--16.21) |
| Action refresh | 0.68 (0.35--1.02) | 0.88 ms (0.58--1.18) |

The complete-loop latency mean was 253.37 ms per turn across the two games
(observed game means 152.19 and 354.55 ms). Route queries are therefore
measurable but remain a small part of the current loop budget.

## Retained replay

All eight route-enabled snapshots having both a defence proposal and its
scored candidate set were retained in
`benchmarks/gdo/captured_snapshots/city_defense_native_160/`.

- Manifest:
  `benchmarks/gdo/captured_snapshots/city_defense_native_160_manifest.json`
- Manifest structural hash:
  `56bc2234ddd6bcfcc280aae478b7a573116ecca2314a2ef2a24ccb28e4e4d687`
- Manifest file SHA-256:
  `76fb86e9f1045cab8931b33422e0aaa033c8d9c2733d43a6b9340203bca59773`
- Diagnostic report:
  `benchmarks/gdo/gdo4_city_defense_native_160_diagnostic.json`
- Report structural hash:
  `ce1089ee00744696441fce4373cc53ce32365f542fbf4d52ba96c1295cacf949`
- Report file SHA-256:
  `5163a3a9d58b0a3ca0879b33c3bb0f913e189b23de5a27e34fe343ce7b38cd53`

The replay passed structural validation and produced:

| Diagnostic | B1 scalar readout | B4 exact typed readout |
|---|---:|---:|
| Covered threat slots, current-action readout | 1 | 7 |
| Uncovered threat slots, current-action readout | 19 | 13 |
| Selected operations, current-action readout | 1 | 7 |
| Covered threat slots, full intent assignment | not applicable | 12 |
| Uncovered threat slots, full intent assignment | not applicable | 8 |

All 32 observed threats had supported value estimates. Nine of 13 requirements
had at least one supported operation edge, or 69.23%, compared with 5 of 12
(41.67%) in the prior fresh grounded capture. All replay candidates were
represented in the typed candidate edge set, no actor, production, late, or
sole-defender safety violations occurred, and replay p95 was 12.19 ms.

## Interpretation and remaining gate

The native route boundary fixed a real grounding failure: multi-turn defender
movement can now use an exact current server ETA rather than assuming adjacency
or abstaining. The improved edge coverage and B1-to-B4 readout difference show
that the new input reaches the intended mechanism.

GDO-4 is not closed. Supported operation-edge coverage is 69.23%, below the
frozen 90% gate. The exact assignment ties the identity-aware greedy
assignment, so it has not established an optimizer advantage. The replay still
lacks authoritative enemy threat ETA and counterfactual operation outcomes,
and intent assignment cannot be credited as executed gameplay. The next
correctness target is deadline-safe threat reachability and a decision-safe
current-action readout, followed by a paired engine-live policy ablation.
