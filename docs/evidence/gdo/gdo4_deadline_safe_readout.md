# GDO-4 deadline-safe threat and readout hardening

Status: replay validation passed; shadow-only
Date: 2026-07-30
Source cohort: `gdo4-native-routes-160-20260730`

## Problem

The initial city-defence threat model calculated the earliest attack turn as
one tile per turn:

```text
current turn + max(0, tile distance - 1)
```

That assumption was unsafe. All 32 threats in the retained native-route cohort
are Ironclads, Destroyers, or Cruisers with ruleset move rates between four and
six tiles per turn. The old deadline could therefore accept a defender that
would arrive after a fast visible attacker.

The readout also used “supported operation edge” as both an actionability
measure and an epistemic-coverage measure. A known late route was counted the
same way as a missing route estimate. That made the 90% typed-estimate gate
semantically incorrect.

## Correction

`CityDefenseAnalyzer` version 1.2 now:

- derives a conservative earliest-attack lower bound from ruleset move rate;
- records the move rate and ETA basis on every visible threat;
- marks missing move rate as uncertainty rather than fabricating a deadline;
- uses the exact native own-unit route to reject an alternate first step when
  the native-selected route is advertised and already supplies the
  decision-equivalent action;
- uses a native route deadline miss to reject geometrically optimistic
  alternate steps;
- retains native unreachable, late, protected, and missing-route outcomes as
  distinct reason codes;
- marks missing emergency-production ETA as unknown rather than “known late.”

The shared `grounded_operation_result()` classifier now separates:

- supported positive operations;
- grounded negative or protected results;
- epistemically unresolved operations.

The runtime shadow payload reports actionability, grounded operation coverage,
and decision-resolved requirement coverage separately. It may label a selected
shadow readout decision-safe only when assignment is exact and threat,
operation, and requirement coverage each meet 90%. Live authority and live
ordering remain unchanged.

The audit also found and repaired a compatibility regression in the earlier
route foundation. An empty optional route collection had changed the frozen
snapshot identity. Route-disabled and explicitly empty inputs now retain their
legacy state hash; only non-empty exact route bytes join the identity. The
scalar-v1 golden corpus again reproduces byte-exactly.

## Replay result

The corrected 8-fixture replay has:

| Measure | Before deadline correction | After correction |
|---|---:|---:|
| Threats | 32 | 32 |
| Threat deadlines advanced | 0 | 15 |
| Supported positive operations | 45 | 35 |
| Known late operations | 55 | 65 |
| Native-route-bounded negative results | 0 | 71 |
| Unresolved route results | 79 | 0 |
| Actionable requirements | 9/13 | 7/13 |
| Grounded operation comparisons | not separated | 192/192 |
| Decision-resolved requirements | not separated | 13/13 |
| B4 one-action covered slots | 7 | 7 |
| B4 full-intent covered slots | 12 | 8 |

The lower B4 full-intent figure is a correctness result: four assignments that
appeared feasible under the slow-attacker assumption miss a conservative
deadline. The current-action B4 readout is unchanged, so the correction removes
unsafe future credit without reducing the already selected action set in this
cohort.

The exact solver remains tied with identity-aware greedy on coverage and
objective value. This replay therefore does not establish optimizer advantage,
operation completion benefit, or gameplay-score benefit.

## Remaining work

The lower bound intentionally assumes the fastest geometrically possible
approach. It does not prove that a naval unit can traverse the intervening map
or execute the relevant city attack. The next grounded input should be a
player-information-safe threat reachability probe or an independently
validated supported-subset model. After that, operation completion and
counterfactual loss evidence are required before any city-defence live pilot.
