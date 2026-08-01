# FDAS Phase 7 persistent combat operation projection

Status: component-only, shadow-only, no policy authority.

This increment adapts the existing atomic combat lifecycle to the generic FDAS
operation projection. A selected combat operation retains its stable two-actor
conditional specification in `OperationStore`; the adapter exposes the current
step, target requirement, conservative interval/material requirement,
byte-identical legal action, and exact typed resource claims.

At step zero the projected reservation is the whole-operation atomic claim:
both participants, action budget, and exclusive target identity remain one
scheduler decision. If the first attack is accepted and the target survives,
the existing lifecycle advances authoritatively to the conditional second step
and reserves only that step's claims. The focused tests verify the operation
AtomSpace changes current step and legal binding accordingly.

Immediately after an accepted action, the same-snapshot binding and claims are
removed and the RequirementSet records
`awaiting-authoritative-combat-effect`. This prevents the still-advertised
action from being mistaken for another authorized attempt before a newer
snapshot resolves the effect.

Boundaries of this increment:

- all combat selection, probability, material, and resource decisions remain
  in the existing tested combat assembler/lifecycle;
- the adapter sends no action and creates no new combat authority;
- protected garrison/escort/transport conflicts require upstream resource
  claims before they can participate in the shared scheduler;
- no FDAS authority flag is enabled.

Verification:

```text
pytest -q Autotests/test_freeciv_combat_operations.py \
  Autotests/test_freeciv_fdas_operations.py

28 passed
```
