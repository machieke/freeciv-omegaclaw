# GDO-3 identity/time resource shadow evidence

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

Authority: disabled; diagnostic shadow only

## Result

GDO-3 implements and validates the identity- and time-bearing resource layer
required by the grounded implementation plan:

- typed resource identities and half-open turn windows;
- hard-current, conditional-future, and advisory claims;
- authoritative current-snapshot capacity extraction;
- byte-compatible adapters from v1 packet costs and budgets;
- deterministic greedy and bounded-exact schedulers;
- an exact saturated-budget fast path;
- reservation, commit, release, expiry, and capacity-reconciliation lifecycle;
- commit-validator integration;
- default-off asynchronous shadow comparison with the existing packet scheduler;
- explicit post-decision worker dispatch;
- versioned capacity, request, reservation, rejection, release, and scheduler
  events with full resource identity and attributable reasons.

The implementation does not grant resource scheduling policy authority. The
live scalar-v2 action ordering and packet schedule remain unchanged.

## Paired diagnostic

The retained report is
`benchmarks/gdo/gdo3_resource_shadow_diagnostic.json`.

Protocol:

- 200 measured pairs after 20 warm-up pairs;
- fresh snapshot identity for every pair;
- alternating arm order;
- paired garbage-collection stabilization;
- baseline: scalar PF-v2 plus v1 packet scheduling;
- treatment: the same live controller plus default-off-authority GDO-3 shadow;
- the resource worker completes before the next arm, preventing worker compute
  from contaminating its paired comparator;
- worker latency is reported separately from the complete live planning
  boundary.

Measured p95:

| Boundary | p95 |
| --- | ---: |
| scalar-v2 live planning | 15.028 ms |
| scalar-v2 plus resource-shadow dispatch | 14.989 ms |
| observed live p95 delta | -0.039 ms (-0.260%) |
| deferred resource worker | 19.808 ms |

The small negative live delta is measurement noise, not a speedup claim.

All declared gates passed:

- every fresh batch completed;
- zero queue-capacity rejections and zero worker failures;
- byte-identical live actions;
- identical live candidate ordering;
- identical scalar schedule;
- exact and packet selection agreed on every measured fixture;
- zero hard-capacity violations;
- every rejection had a reason and capacity conflicts named the resource;
- completed schedule artifacts were deterministic;
- p95 live overhead remained below both 15% and 50 ms;
- policy authority remained false.

Report hash:
`27c6981cc99df81ca206efb1f34cbff63ebc0779be7ccee25381fb0e9766e4bb`.

## Correctness evidence

The focused contracts cover:

- two operations claiming one actor;
- two ferry seats versus three passengers;
- overlapping and non-overlapping turn windows;
- exclusive tile occupancy;
- treasury quantities;
- hard-current versus conditional-future claims;
- capacity disappearance and deterministic reconciliation;
- commit rejection releasing claims;
- exact scheduling beating a greedy knapsack counterexample;
- deterministic node-limit fallback;
- input-permutation invariance;
- an exact analytical saturated-budget path;
- 200 deterministic exhaustive small-knapsack comparisons;
- resource event schema validation and final-drain emission.

The complete FreeCiv regression command:

```text
python3 -m pytest -q Autotests/test_freeciv_*.py
```

Result: `871 passed in 328.37s`.

## Interpretation and limitations

This is a mechanism claim, not a FreeCiv score or win-rate claim. The retained
fixture demonstrates current-turn actor/controller conflicts and the
packet-compatibility boundary. It does not yet provide a diverse captured
multi-turn corpus containing ferry, contested-tile, treasury-spend, research,
and diplomatic conflicts.

Conditional-future claims remain feasibility information and cannot manufacture
future authority. Tile and diplomatic capacity are omitted unless an
authoritative ruleset/state source exists. Transport seats are exposed only
when ruleset capacity and visible current load are both available.

The next scientific step is GDO-4: apply grounded threat estimates and
identity-aware assignment to the bounded city-defence domain, retaining exact
legal-action revalidation and scalar-v2 fallback for unsupported comparisons.
