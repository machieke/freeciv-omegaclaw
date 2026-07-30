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
  `28f04eba01282794c0805d4ecc61f29896246b64e18e20d6272b9d27cb3e00ee`
- Report file SHA-256:
  `460224f6cba03bdcca48870e5c90ee92b0ba50357129bb69b97a7ac4c0f4f67a`

The replay passed structural validation and produced:

| Diagnostic | B1 scalar readout | B4 exact typed readout |
|---|---:|---:|
| Covered threat slots, current-action readout | 1 | 7 |
| Uncovered threat slots, current-action readout | 19 | 13 |
| Selected operations, current-action readout | 1 | 7 |
| Covered threat slots, full intent assignment | not applicable | 8 |
| Uncovered threat slots, full intent assignment | not applicable | 12 |

All 32 observed threats had supported value estimates. The original
route-enabled diagnostic classified 9/13 requirements as actionable, but that
used a speed-1 threat deadline and was optimistic. The corrected ruleset-rate
lower bound advances 15/32 threat deadlines by one turn and leaves 7/13
requirements with a timely action. It rejects 10 previously admitted late
operations.

This is not missing estimate coverage. All 192 operation comparisons and all
13 requirements now have decision-grounded positive or negative results:
feasible, late, native-route deadline miss, protected, or a non-native
alternate dominated by the advertised native route. All replay candidates
were represented in the typed candidate edge set, no actor, production, late,
or sole-defender safety violations occurred, and replay p95 was 12.68 ms.

## Interpretation and remaining gate

The native route boundary fixed a real grounding failure: multi-turn defender
movement can now use an exact current server ETA rather than assuming adjacency
or abstaining. The improved edge coverage and B1-to-B4 readout difference show
that the new input reaches the intended mechanism.

GDO-4 is not closed. The corrected readout now separates epistemic coverage
(100%) from actionability (53.85%); genuinely impossible deadlines no longer
masquerade as missing estimates. The exact assignment ties the identity-aware
greedy assignment, so it has not established an optimizer advantage. The
ruleset-rate ETA is a conservative geometric lower bound rather than native
enemy path parity. The replay also lacks counterfactual operation outcomes,
and intent assignment cannot be credited as executed gameplay. The next
correctness target is authoritative or probe-validated threat reachability and
operation completion evidence, followed by a paired engine-live policy
ablation.
