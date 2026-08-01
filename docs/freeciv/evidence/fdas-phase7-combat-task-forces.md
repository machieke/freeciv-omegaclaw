# FDAS Phase 7 combat and task-force projection

Status: component-only, shadow-only, no policy authority.

This increment projects one bounded `combat-engagement` scope for each current
native Freeciv action-probability result. The scope retains the exact actor,
target tile, packet-visible target when still present, and a byte-identical
legal attack when one remains advertised. A target disappearing from packet
visibility removes the visible-target and action readouts without deleting the
underlying historical/current-revision probability packet projection.

Every bounded action interval is represented as a conservative partition in
its support witness:

- success lower bound;
- failure lower bound;
- residual unknown mass (`upper - lower`);
- total probability of one.

Non-bounded native statuses remain explicitly unknown. Numeric interval values
stay in witnesses rather than becoming identity-bearing scalar atoms.

The projector also reuses `CombatOperationAssembler` to open a `task-force`
scope only for a fully grounded two-participant conditional attack. This keeps
the existing ruleset material model, target visibility checks, exact legal
actions, and explicit “second attack given first failure” semantics. The
combined interval likewise retains residual unknown mass and is not treated as
independent attacks or a point estimate.

Boundaries of this increment:

- raw native intervals are observations, not recommendations;
- task-force creation requires the existing positive conservative material
  readout and does not add a new combat policy;
- combat execution, reservations, protected-garrison constraints, and
  lifecycle projection are not added by this slice;
- no FDAS authority flag is enabled.

Verification:

```text
pytest -q Autotests/test_freeciv_fdas_combat.py \
  Autotests/test_freeciv_fdas_phase0.py \
  Autotests/test_freeciv_combat_operations.py

214 passed in the broad FDAS/operation/resource/transport/combat regression.
```
