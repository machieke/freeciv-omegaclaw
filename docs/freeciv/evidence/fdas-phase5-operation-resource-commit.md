# FDAS Phase 5 evidence: operation, resource, and commit boundaries

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capabilities: component-only  
Policy authority: disabled

## Realized scope

This increment realizes the component portions of PR 12 and the fail-closed
input boundary needed before PR 13:

- `OperationSpec` and `OperationProgress` are projected into typed operation
  microspaces, including type, goals, participants and roles, target, steps,
  requirements, completion predicates, ruleset digest, current step, state,
  and lifecycle reasons;
- immutable specification atoms depend only on the operation-spec revision,
  while state/current-step atoms also depend on the progress revision;
- an explicit same-snapshot rematerialization path handles durable-store
  changes without weakening ordinary idempotent snapshot updates;
- composite domain projectors merge compatible singleton scopes and keep
  independently gated domain records transactional;
- action-mode FDAS candidates map their exact resource identities to current
  hard claims and authoritative one-turn capacities;
- the bounded exact resource scheduler exposes exclusive conflicts and stable
  operation attribution;
- action and CPU packet costs are scheduled only from explicit caller-supplied
  budgets; diagnostic routes use CPU/expansion costs and never consume action
  resources;
- FDAS commit bindings carry snapshot/legal-action identity, revision/build
  identity, candidate/operation hashes, and exact deficit support IDs;
- the commit validator rechecks every identity and support, rejects causal
  blockers, and finally rejects the current candidates at the domain-authority
  gate because the branch remains shadow-only;
- a strict configuration profile rejects unknown fields, invalid budgets,
  global/domain authority inconsistencies, and activation requests above the
  manifest's declared capability level.

No resource reservation is written to the durable ledger, no plan is
materialized, and no action is authorized by this increment.

## Verification

The focused configuration, projection, pressure, scheduling, and commit tests
passed as part of a 31-test FDAS slice. The tests cover:

- operation field coverage and typed namespace/authority constraints;
- progress-only invalidation and rematerialization;
- quarantine rejection;
- resource exclusivity and exact single-winner selection;
- packet conservation and joint selection;
- unmapped-resource fail-closed behavior;
- changed revision/candidate rejection;
- causal-blocker and domain-authority firewalls;
- strict default configuration and hypothetical bounded-manifest gating.

A wider FDAS/PF-v2/operation/resource/packet/commit regression then passed:

```text
130 passed in 32.97s
```

The fixture projected three operations into 39 operation atoms with 39 exact
supports. Its composite revision build hash was
`c78e5abefbff6532b227ad8e68cf4d26`.

For two competing governor operations sharing one city-governor slot, 120 warm
resource/packet bridge evaluations produced:

| Measure | Result |
|---|---:|
| Requests | 2 |
| Jointly selected operations | 1 |
| Mean scheduling latency | 0.3812 ms |
| p95 scheduling latency | 0.4225 ms |
| Maximum scheduling latency | 0.6028 ms |

The deterministic resource decision digest was
`a3ed83bf30f9a3749c4c25527afa16f5545f3f6da7009d41e97d72517b10ff80`
and the bridge artifact hash was
`3f8a24cf3d6e56981c761f8cf28fce250b80f87260407d328b1810b7f8ad983e`.

## Claim boundary

This evidence supports exact structural projection and deterministic shadow
arbitration. It does not support bounded authority, gameplay improvement, or a
score/win-rate claim. Bounded authority remains impossible until action effects
are compiled, accepted replay gates exist, and the manifest is deliberately
promoted.
