# FDAS Phase 6 evidence: persistent defense operation reconciliation

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `defense_operation_reconciliation=component-only`  
Policy authority: disabled

## Realized scope

This increment connects existing city-defense domain operations to FDAS without
creating a second lifecycle authority:

- `FdasCityDefenseOperationAdapter` accepts an injected, caller-owned
  `OperationStore` and reuses the existing validated city-defense assembler;
- reinforcement, fortify, hold, interception, and defender-production operation
  types retain their existing immutable step, requirement, deadline, role, and
  completion contracts;
- current exact actions are held in a separate snapshot-scoped binding rather
  than being written into persistent intent or factual truth;
- a later route step with a different domain-edge/action identity reconciles to
  the same persistent operation when type, actor, and target match;
- each current action must be byte-identical to a current advertised legal
  action; otherwise the operation is blocked and no current binding is exposed;
- blocked operations can recover to reservable when a later exact legal binding
  appears;
- authoritative destination occupation and fortification activity can complete
  their respective operations;
- enemy disappearance cannot complete an interception, and defender production
  remains unknown without before/after product identity;
- expiry, store quarantine, duplicate identity, and lagging post-completion
  proposals fail closed;
- `OperationProjector` optionally projects `operation-current-action`,
  `operation-current-action-legal`, and `operation-action-binding` from exact
  current bindings, with both operation-binding and legal-action dependencies;
- a binding from an older snapshot is simply omitted and never converted into
  a negative fact.

The adapter does not reserve resources, activate an operation, submit an action,
or bypass the existing execution gate.

## Verification

The focused lifecycle, operation projection, and operation-store suite passed:

```text
18 passed in 15.83s
```

The full FDAS plus operation-store suite passed before the final lagging-row
hardening:

```text
82 passed in 33.38s
```

The hardening fixture additionally verifies that an analysis row arriving after
the unit is authoritatively observed at its destination does not reopen a new
operation.

## Claim boundary

This is structural shadow reconciliation. Resource reservation and action
acceptance remain owned by the existing lifecycle/scheduler/execution path, and
no defense authority or gameplay/score claim follows from this evidence.
