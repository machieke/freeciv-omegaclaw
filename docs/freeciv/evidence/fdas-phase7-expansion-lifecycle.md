# FDAS Phase 7 expansion lifecycle evidence

Status: component-only; `expansion` authority remains disabled by default.

The shadow `FdasExpansionOperationAdapter` consumes only a same-snapshot FDAS
revision and supports two exact one-step operations:

- found a city at the founder's current, visible, uncontested tile when the
  current settlement scope has no contest, threat, escort, or blocker atom;
- join a colocated city when the population-recovery scope and compiled
  ruleset prove the founder capability and positive integral population gain.

Each reservable operation exposes a RequirementSet, an exclusive founder
claim, a current action-budget claim, and (for founding) a conditional,
exclusive settlement-tile claim. The adapter does not reserve these resources,
select an action, or send an action. It only observes a caller-reported result
for a byte-identical current binding.

Action acceptance transitions the operation to active but releases the
current binding and claims while it waits for authoritative state. Founding
completes only after the founder disappears and an owned city appears on the
exact target tile. Population recovery completes only after the founder
disappears and the exact target city reaches its ruleset-derived baseline plus
gain. Founder consumption without the required effect is an explicit failure;
missing effects expire after a bounded observation window.

`Autotests/test_freeciv_fdas_expansion_lifecycle.py` covers the operation atom
projection, resource identities, unsafe-site omission, acceptance/effect
separation, both successful effects, wrong-effect failure, and stale-revision
rejection.
