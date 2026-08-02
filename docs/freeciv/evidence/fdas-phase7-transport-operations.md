# FDAS Phase 7 persistent transport operation projection

Status: component-only, shadow-only, no policy authority.

This increment adapts the existing founder/ferry operation assembler and
lifecycle into the generic FDAS operation projection. It does not duplicate
route, load, scheduling, or lifecycle logic. The adapter exposes the durable
`OperationStore` records together with a revision-current RequirementSet,
typed `ResourceClaim` rows, and a byte-identical legal-action binding.

The binding is present only when:

- the existing transport readout says the current phase is reservable;
- the action remains in the current legal-action packet;
- the exact lifecycle reservation is active for the current snapshot and its
  claims equal the freshly derived current-step claims;
- the persistent operation is reserved or active.

After an action is accepted, its reservation is released and the adapter emits
no binding or resource claims in the same snapshot. The RequirementSet instead
records `awaiting-authoritative-step-effect`. A later authoritative snapshot
may satisfy the completion predicate and advance the operation, or cause the
existing lifecycle to block/re-estimate it. The focused regression verifies an
embark step advancing to a ferry route step and receiving a new exact binding.

The operation projection contains the current step, participants, deadline,
RequirementSet premises and roles, typed resource identities/windows, and the
current legal binding. Existing exact scheduling remains authoritative over
reservations; FDAS remains an inspectable shadow projection.

## Durable restart boundary

The lifecycle is now stored as one atomic, digest-verified bundle containing
the `OperationStore`, canonical founder/ferry assemblies, the bounded repair
count, and pending settlement-retention observations. Assembly serialization
round-trips the immutable operation specification, stable intent,
RequirementSet, initial grounded readout, native corridors, and typed resource
request, with nested spec, corridor, and assembly digest verification.

Resource reservations are deliberately excluded from persistence because they
are facts about one exact authoritative snapshot. On restart:

- a reserved operation on the identical snapshot must reproduce the exact
  legal action, resource claims, and capacity schedule before its reservation
  and FDAS binding are reconstructed;
- an active operation on the identical snapshot remains unbound while waiting
  for a newer authoritative effect;
- a newer snapshot is passed through normal effect observation, step
  advancement, blocking, and re-estimation;
- partially transitioned (`proposed` or `reservable`) persisted state fails
  closed;
- identity, schema, authority-boundary, digest, record/assembly, or repair
  metadata corruption quarantines the entire lifecycle without rewriting the
  source file.

This closes restart reconstruction for the component. It does not add intent
discovery, live runtime wiring, action authority, or a gameplay claim.

Boundaries of this increment:

- intent discovery and settlement-site ranking are not implemented here;
- no new repair policy or transport risk estimate is introduced;
- escort and fleet-defense requirements remain unavailable;
- the adapter does not send actions and no FDAS authority flag is enabled.

Verification:

```text
pytest -q Autotests/test_freeciv_transport_operations.py \
  Autotests/test_freeciv_operations.py \
  Autotests/test_freeciv_fdas_corridor.py \
  Autotests/test_freeciv_resource_claims.py \
  Autotests/test_freeciv_identity_resource_shadow.py \
  Autotests/test_freeciv_fdas_operations.py

45 passed
```
