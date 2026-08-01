# FDAS Phase 6 evidence: unit and city-defense shadow foundation

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `unit_domain_projection=component-only`  
Policy authority: disabled

## Realized scope

This increment establishes the first Phase-6 city-defense causal substrate:

- each own unit receives a bounded unit-facts microspace;
- ruleset attack, defense, hitpoint, firepower, movement-class, and defender
  classification are exposed through typed dependency-declaring groundings;
- persistent-combat and persistent-land-defense capabilities are deterministic
  derived facts, never authoritative unit state;
- city required-garrison and current local-garrison counts reproduce the
  existing policy calculation, including the disorder and observed martial-law
  branches;
- city garrison coverage and deficit are mutually exclusive factual policy
  conditions with exact snapshot, ruleset, and policy dependencies;
- local defenders are linked to protected cities, and sole/required defenders
  receive an explicit removal-protection relation;
- a server-advertised fortify action creates a fortification-opportunity fact
  but does not manufacture a survival deficit;
- visible foreign units are packet observations; a city-visible-threat relation
  is produced only when coordinates and both map-wrap flags provide an exact
  topology witness;
- topology absence remains unknown: no `not-threatened` or enemy-absence atom is
  emitted;
- a city-garrison deficit instantiates a survival goal and regresses to a
  byte-identical legal unit move only when the actor has a grounded defender
  capability and the move reaches the exact city coordinates;
- moving a sole source-city defender is explicitly blocked, and the still
  unknown action effect keeps the route on diagnostic expansion with zero act
  pressure.

The slice does not yet implement route-ETA groundings, replacement movements,
defender production before a threat deadline, durable reinforcement lifecycle,
episode attribution, or bounded defense authority.

## Verification

Seven focused unit-defense tests cover ruleset parity, garrison parity,
legacy-view preservation, fortify/deficit separation, cold/incremental
equivalence after defender removal, closed-world threat safety, and protected
source-garrison regression. The combined city, unit-defense, and FDAS pressure
slice passed:

```text
26 passed in 17.09s
```

The wider FDAS/PF-v2/operation/resource/packet/commit regression passed:

```text
137 passed in 33.62s
```

On the one-city/one-unit baseline fixture, 120 independent cold composite
builds produced:

| Measure | Result |
|---|---:|
| Unit-defense domain atoms | 6 |
| Unit scopes | 1 |
| Mean cold build | 30.5900 ms |
| p95 cold build | 45.0583 ms |
| Maximum cold build | 47.7719 ms |

The deterministic build hash was
`3caec7e9417b41e1cb957b55a1c582f2`.

## Claim boundary

This is a component-only causal and safety representation. It supports no live
authority or gameplay/score claim. In particular, candidate action effects are
still explicit unknowns, so every movement route remains behind the causal
firewall.
