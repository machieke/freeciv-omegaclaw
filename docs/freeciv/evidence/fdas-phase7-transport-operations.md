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

Boundaries of this increment:

- intent discovery and settlement-site ranking are not implemented here;
- no new repair policy or transport risk estimate is introduced;
- escort and fleet-defense requirements remain unavailable;
- the adapter does not send actions and no FDAS authority flag is enabled.

Verification:

```text
pytest -q Autotests/test_freeciv_transport_operations.py \
  Autotests/test_freeciv_fdas_operations.py \
  Autotests/test_freeciv_fdas_replacement_lifecycle.py

19 passed
```
