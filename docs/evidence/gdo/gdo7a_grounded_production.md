# GDO-7A grounded production enabling operations

Status: retained mechanism gate passed; fresh execution and policy-benefit
gates remain open

Date: 2026-07-30

Branch: `experimental/pln-pressure–bridge–fluid`

## Claim boundary

The GDO-7A slice now grounds the current city queue action, compiler-backed
shield cost and upkeep, current-rate completion bounds, explicit switch-cost
uncertainty, city production-slot identity, and a persistent two-step
queue/observed-product lifecycle.

The retained replay shows a concrete correctness improvement over the
immediate simpler baseline: 22 of 42 production candidates claimed zero-turn
completion after switching the city target. The grounded model makes zero
zero-turn product claims and always reports that the queued unit or building
is unavailable until a later authoritative snapshot supplies its identity.

This is a decision-safety mechanism result, not an engine-backed outcome or
score result. The operation remains `policy_authority=false`. The retained
corpus does not contain enough typed post-completion unit/building state to
claim ETA calibration, improved production completion rate, score benefit, or
win-rate benefit.

## Current-step transition model

`GroundedProductionTransitionModel` accepts only the narrow subset where:

- the exact `city_production` action bytes are advertised by the server;
- the city exists and is owned by the current player;
- authoritative city buildability contains one matching kind, numeric ID, and
  name;
- one compiled ruleset target supplies build cost, population cost, unit or
  building upkeep, unit class, flags, and roles;
- current production kind/value, shield stock, and shield surplus are present.

The emitted transition is the queue-selection step. Its goal cost-to-go is
unchanged and its completion turn is the current turn because it represents
the accepted queue command, not the future product. The artifact separately
contains a constant-current-rate completion bound.

If the target is already selected, current shield stock is retained and the
constant-rate ETA has one value. If the action switches the target, the model
does not guess the Freeciv production penalty. Snapshot schema v1 does not
expose:

- `before_change_shields`;
- `changed_from`;
- `last_turns_shield_surplus`;
- `caravan_shields`;
- `disbanded_shields`.

Those fields are read by Freeciv's `city_change_production_penalty()`. The
model therefore reports unresolved switch cost, permits an earliest
completion of one turn, and derives a conservative latest constant-rate bound
from zero retained shields. A nonpositive current shield rate is explicitly
reported as stalled rather than converted into a fabricated ETA.

## Enabling operation and resources

`ProductionEnablingOperationAssembler` forms an identity-bearing operation
such as:

```text
BUILD_DEFENDER
    step 0: select exact city queue target
    step 1: observe exact product identity
    dependency: downstream city-defence operation
```

Its `RequirementSet` binds city ownership, advertised action, buildability,
ruleset profile, completion forecast, and downstream dependency. An emergency
operation is assembled only when the conservative latest completion bound
fits its declared deadline.

A queue switch claims the exact city production slot and one controller action
slot as `HARD_CURRENT`. Continued use of the city slot and post-completion gold
or building upkeep are represented as `CONDITIONAL_FUTURE`. They remain
diagnostic until a future snapshot can provide time-matching authoritative
capacity; they do not manufacture a future reservation.

The lifecycle:

1. reserves and revalidates the exact queue action;
2. attributes an accepted or rejected engine action;
3. requires the selected kind/value to appear in a newer snapshot;
4. waits without exposing an in-progress unit as a participant;
5. blocks visibly if the target diverges or shield output stalls;
6. repairs only when a newer snapshot restores the target and positive output;
7. completes only when a new home-city/type unit identity or building identity
   is observed;
8. marks the declared downstream operation ready only at that completion.

The lifecycle also fails closed when an accepted queue action has no observed
effect and releases current-step reservations immediately after commit.

## Retained mechanism replay

Command:

```bash
python3 scripts/run_gdo_production_replay.py \
  --manifest benchmarks/gdo/captured_snapshots/city_defense_grounded_160_manifest.json \
  --ruleset-root build/freeciv/ruleset-source \
  --iterations 20 \
  --output benchmarks/gdo/gdo7a_production_grounding_diagnostic.json
```

The 13 retained player-visible engine fixtures contain 42 production
candidates. Results:

| Metric | Result |
| --- | ---: |
| grounded estimates emitted | 42 / 42 |
| compiled build-cost parity | 42 / 42 |
| legacy zero-turn completion ETAs | 22 |
| legacy zero-turn ETAs on switches | 22 |
| grounded zero-turn product claims | 0 |
| grounded `product_available_now=true` claims | 0 |
| switches with missing history exposed | 42 |
| deterministic repeated estimates | yes |
| estimator mean latency | 0.421 ms |
| estimator p95 latency | 0.447 ms |

The generated report's semantic `report_hash` is:

```text
dc3d1465b2e1afb478f927ccfda7b79393ee9c15118a21d7f70d95a5f7da801d
```

The file SHA-256 is:

```text
8933ee888891a5c65017dcc517d5da27934f7c08f98b45ed4c791fa0b71e6067
```

## Decision

The production subdomain passes its retained decision-safety mechanism gate:
it eliminates the simpler baseline's impossible zero-turn product semantics,
grounds all retained candidate costs, and makes product identity contingent on
later observation. The slice stays shadow-only.

The remaining GDO-7A evidence gate is a fresh engine cohort that exercises
queue switch, accepted-action attribution, product completion, deadline
coverage, stall/repair, upkeep observation, and downstream activation. Only
after that cohort beats the immediate baseline on completion/deadline
correctness should production receive any authority.
