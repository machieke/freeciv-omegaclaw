# FDAS Phase 7 aggregate acceptance report

Date: 2026-08-01  
Branch: `experimental/functional-dependent-atomspace`  
Acceptance level: component-only / shadow; no bounded or engine authority

## Scope accepted at component level

| Sub-slice | Capability declarations | Evidence |
|---|---|---|
| Region and routes | `region_domain_projection`, `route_corridor_projection` | bounded current city regions and exact native route-corridor scopes |
| Settlement and escort | `settlement_site_projection`, `settlement_escort_reachability` | visible-current safety, fog as unknown, exact threat/escort reachability |
| Population recovery | `population_recovery_projection` | ruleset-exact founder join capability and population gain |
| Expansion lifecycle | `expansion_operation_projection` | persistent found-city and population-recovery effects |
| Transport | `transport_capability_projection`, `transport_operation_projection` | exact carrier/load/seat identity and existing multimodal lifecycle projection |
| Combat | `combat_task_force_projection`, `combat_operation_projection` | conservative intervals with unknown mass and existing atomic lifecycle projection |

## Exit-criterion disposition

- Safe settlement is not delayed by fabricated escort logic: a founding
  operation requires a positive visible-current uncontested proof and is
  omitted under fog, contest, visible threat, escort requirement, or blocker.
- Fog does not become certainty: `currently-uncontested` depends on explicit
  current visibility and closed visible-enemy membership.
- Transport seats cannot be double-claimed: capability and scheduler use the
  same `transport_seat` resource identity; activation remains owned by the
  existing exact reservation ledger.
- Combat predictions retain unknown mass: bounded success/failure lower bounds
  and residual mass form an explicit conservative partition.
- Expansion exits and recovery are explicit: action acceptance only activates
  an operation; later founder consumption plus the exact city effect completes
  it. Wrong effects fail and absent effects expire.
- Expansion, transport, and combat have independent configuration flags. The
  validator now requires every named sub-capability plus the common pressure,
  resource, and exact-commit gates to be `bounded-authority` before accepting
  any of those flags.

## Verification

The aggregate regression command at this boundary was:

```text
pytest -q Autotests/test_freeciv_fdas_*.py \
  Autotests/test_freeciv_operations.py \
  Autotests/test_freeciv_operation_lifecycle_report.py \
  Autotests/test_freeciv_city_defense_assignment.py \
  Autotests/test_freeciv_city_defense_replay.py \
  Autotests/test_freeciv_resource_claims.py \
  Autotests/test_freeciv_grounded_movement.py \
  Autotests/test_freeciv_transport_operations.py \
  Autotests/test_freeciv_combat_operations.py
```

Result: `229 passed`.

## Non-claims and authority decision

This is component acceptance, not a score, win-rate, replay-parity, live safety,
or engine-performance claim. Existing imperative controllers remain the
control and action path. `authority_enabled` and every `domain_authority` flag
remain false. Promotion requires fresh domain-specific replay/safety evidence,
current commit revalidation, and an explicit manifest upgrade; this report does
not authorize such an upgrade.
