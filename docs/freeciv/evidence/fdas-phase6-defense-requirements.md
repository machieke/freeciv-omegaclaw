# FDAS Phase 6 evidence: defense requirements and resource claims

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Capability: `defense_requirement_projection=component-only`  
Policy authority: disabled

## Realized scope

This increment makes the current structural constraints of a selected
city-defense operation explicit without granting scheduling or execution
authority:

- each reconciled current defense step owns one conjunctive `RequirementSet`;
- capability, source availability/garrison protection, native route, deadline,
  exact legal binding, and resource capacity are distinct premise roles;
- a known failure is linked to its exact premise and operation blocker;
- a current executable unit action carries an exclusive `hard_current` actor
  claim for the current turn window;
- defender production carries the same bounded claim on the exact city
  production slot;
- blocked candidates retain their machine-readable premise failure but carry no
  resource claim;
- operation scopes expose the immutable operation deadline, requirement set,
  premise roles/blockers, and the complete resource identity, kind, owner,
  scope, subresource, quantity, exclusivity, hardness, and turn window;
- all current requirement/claim relations depend on an integrity-checked
  `operation-requirements` fingerprint;
- stale snapshot contexts fail closed by omission and are never projected as
  negative facts;
- completion, expiry, or loss of the current assignment clears transient
  bindings and requirement contexts.

## Verification

Focused lifecycle, projection, catalog, and manifest tests cover:

- a persistent multi-turn reinforcement operation whose exact legal action and
  requirement context refresh on the next snapshot;
- actor resource identity and current-turn exclusivity;
- exact city-production-slot identity;
- explicit illegal-action blockers with no blocked resource claim;
- stale binding, requirement, and claim omission;
- context removal on observed completion;
- operation-catalog and capability-manifest parity.

## Claim boundary

The claims are structural scheduling inputs, not reservations. This increment
does not mutate an execution ledger, authorize an operation, enable FDAS policy
authority, or establish gameplay/score improvement.
