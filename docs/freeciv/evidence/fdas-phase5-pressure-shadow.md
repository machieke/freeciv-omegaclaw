# FDAS Phase 5 evidence: pressure shadow adapter

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `dependent_atom_pressure_adapter=component-only`  
Policy authority: disabled

## Realized scope

This increment implements the PR-11/Phase-5 shadow pressure boundary over the
city/economy FDAS slice:

- local desired targets and factual deficit witnesses are materialized as
  separate pressure atoms;
- candidate operations are connected to their exact goal route with revision,
  deficit, explanation, candidate, and operation-spec provenance;
- candidates whose ruleset action effects remain unknown are diagnostic routes
  with `infer`/`expand` resolvability and zero `act` resolvability;
- a legal-bound route with a compiled-effect contract can carry procedural act
  pressure, but its payload and the complete context remain explicitly
  shadow-only and authority-ineligible;
- missing legal causal routes produce explicit gap-expansion operations;
- per-goal effects are explicit, preventing unrelated goals from receiving an
  operation's default effect;
- atom, rule, and operation budgets fail with deterministic truncation
  diagnostics; exhaustion before a complete target/deficit pair returns
  `unknown` without an orphan false target;
- PF-v2 propagation and scheduling do not mutate the source FDAS revision.

The adapter does not yet project operation lifecycles, arbitrate typed game
resources, extend commit validation, or grant bounded city authority. Those are
separate Phase-5 increments and remain gated off.

## Verification

The focused FDAS and PF-v2 suite passed:

```text
74 passed in 31.51s
```

Coverage includes deterministic artifact reproduction, source-revision
immutability, causal-firewall behavior for unknown effects, the future
procedural-route boundary, stale-snapshot rejection, and budget-exhaustion
semantics.

On the five-deficit city/economy fixture, 120 repeated warm evaluations
produced:

| Measure | Result |
|---|---:|
| Local goals | 5 |
| Legal-bound shadow candidates | 4 |
| Pressure atoms | 15 |
| Pressure rules | 5 |
| Scheduled shadow operations | 5 |
| Explicit route gaps | 1 |
| Mean adapter evaluation | 2.7916 ms |
| p95 adapter evaluation | 2.8795 ms |
| Maximum adapter evaluation | 3.1454 ms |

The deterministic context hash was
`2d7f5ae803aec9522360d82cb12257dd2dbcec5ab94c08d79ec8063fa39a662b`
and the evaluation hash was
`80ab31c2f89a34532a6ee76b5bba71c83383c0cae77eb2cc975c50bc3f1c9483`.
The selected route was the explicit missing-route expansion; no action route
was eligible.

## Claim boundary

This evidence supports a deterministic, bounded, truth-safe pressure shadow
component. It does not support a behavior, score, win-rate, or authority claim.
