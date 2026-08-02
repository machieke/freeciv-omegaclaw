# FDAS PR 14: defense-focused shadow activation

Date: 2026-08-02
Branch: `experimental/functional-dependent-atomspace`
Status: declared `shadow-live`; policy authority disabled

## Acceptance boundary

PR 14 does not require a new defense model. The Phase 6 increments already
implement the required unit and region projectors, exact native movement and
defense groundings, persistent reinforcement/replacement operation
reconciliation, current requirements/resource claims, and focused region
activation. Their detailed fixtures and limitations remain recorded in the
`fdas-phase6-*.md` evidence series.

The remaining integration gap was an activation pair whose declared boundary
matches that realized code. This increment adds:

- `profile/dependent_atomspace_defense_shadow.yaml`, which enables only the
  ruleset, city/economy, unit, bounded region, and durable operation
  projections needed by the defense slice;
- `profile/fdas_manifest_defense_shadow.json`, which promotes only the
  exercised dependency, projection, reconciliation, pressure, causal-event,
  and rollback capabilities to `shadow-live`;
- an explicit 5% deterministic cold-verification sample at turn-boundary
  readout;
- selected-support explanation capture and shadow divergence events;
- a configuration fixture proving that all policy, learning, and domain
  authority flags remain false.

The profile deliberately leaves route corridors, settlement, recovery,
transport, combat, opponent belief, episodes, contextual conductance, generic
rules, and every authority slice outside this activation. This keeps PR 14
separate from PR 15 defense authority and episode rollout.

## Acceptance criteria

The defense shadow declaration is acceptable when:

1. the config and manifest validate as an exact schema pair;
2. the runtime contains the city/economy, unit-defense, region, and operation
   projectors and no unrelated focused-domain projector;
3. engine shadow readouts preserve the legacy action trace exactly;
4. sampled cold revisions are equivalent;
5. unit/region/operation scopes and events remain within declared budgets;
6. no FDAS authority event or FDAS-authorized action occurs;
7. rollback to the checked default profile remains configuration-only.

The fresh engine result is appended only after it is run from a clean pinned
commit. Until then this document records activation implementation, not live
acceptance.

## Claim boundary

`shadow-live` means the defense substrate may be constructed, queried,
compared, and explained during an engine game. It does not reserve a unit,
change a planner winner, submit an action, update conductance, attribute an
episode, or support a score/win-rate claim.
