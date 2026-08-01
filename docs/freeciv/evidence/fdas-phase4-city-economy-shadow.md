# FDAS Phase 4 city/economy shadow evidence

Status: passed, component-only

Date: 2026-08-01

Branch: `experimental/functional-dependent-atomspace`

## Claim boundary

FDAS now has an opt-in rich city/economy materialization, local goal factory,
and legally bound shadow operation factory. It is not enabled in the default
snapshot store or live planner. It has no policy or execution authority, and
generic action effects remain explicitly unknown.

## Implemented

- 23 typed city, economy, and research groundings declare input types, output
  units, authority, cache policy, exact dependency paths, witnesses, and
  availability separately from Boolean falsity.
- Groundings cover food/shield stock, production, usage, surplus and output
  vectors; disorder and buildability; production cost and ETA; gold, gross/net
  GPT, upkeep reserve, runway and rates; and research progress, cost, beakers,
  and completion ETA.
- Ruleset-backed cost/ETA results depend on the exact compiled digest and
  target identity.
- The combined projector preserves the byte-exact ten-predicate legacy view
  while adding empire and one compact factual scope per owned city.
- Rich atoms have only typed entity/symbol arguments. No changing numeric
  value enters an ordinary atom argument.
- Authoritative symbolic projection covers current player/turn, research
  target, government, city buildings/governor/disorder/famine, and canonical
  legal action actor/type bindings.
- Dependency-backed derivations cover food security/deficit, order
  stable/deficit, production active/stalled, current queue funded/unfunded,
  treasury safe/below-reserve, and research throughput active/stalled.
- Named policy dependencies reproduce the existing Impact defaults: food
  surplus reserve 1, treasury minimum gold 5, and two-turn upkeep reserve.
- Local goals keep utility, urgency, commitment, risk, and safety separate
  from factual truth.
- Current canonical legal city/governor/rate/research actions can be wrapped as
  deterministic `OperationSpec` shadows with explicit resource identities.
- Unknown generic action effects block authority. Candidate comparison reports
  expose overlap, missing/extra routes, legal binding, authority, and safety.
- `explain` and `why_not` are revision-bound and structurally deterministic.

## Correctness results

| Check | Result |
| --- | ---: |
| targeted regression suite | 195 passed |
| Phase 4 focused tests | 8 passed |
| frozen Phase 0 semantic hash | unchanged |
| rich incremental/cold equivalence | passed |
| exact legacy facade from rich revision | passed |
| ordinary numeric atom arguments | zero |
| unsupported groundings promoted to false | zero |
| shadow candidates absent from legal set | zero |
| shadow authority-eligible candidates | zero |
| policy authority | false |

The queue-funding fixture proves both sides of the condition. A current
Warriors queue with exact cost, positive shield progress, sufficient food, and
treasury runway is `city-queue-funded`; removing shield production retracts it
and produces `city-queue-unfunded`. Its explanation includes both snapshot and
ruleset-digest dependencies.

## Performance

Measured over 120 repetitions on the authoritative-state contract fixture
(one city):

| Measurement | Samples | Mean | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| legacy cold projection | 120 | 1.44 ms | 1.53 ms | 2.23 ms |
| rich city/economy cold projection | 120 | 7.89 ms | 8.20 ms | 16.28 ms |
| rich one-field incremental update | 120 | 8.05 ms | 8.40 ms | 16.83 ms |
| selected-atom explanation query | 120 | 0.05 ms | 0.06 ms | 0.09 ms |

This one-city component is below the 30 ms base-projection and 45 ms eager
materialization targets. Multi-city captured replay and controller-inclusive
latency remain required before shadow-live or authority activation.

## Reproduction

```bash
export FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data
python3 -m pytest -q \
  Autotests/test_freeciv_fdas_city.py \
  Autotests/test_freeciv_fdas_ruleset.py \
  Autotests/test_freeciv_fdas_dependencies.py \
  Autotests/test_freeciv_fdas_core.py \
  Autotests/test_freeciv_fdas_phase0.py \
  Autotests/test_freeciv_state_bridge.py \
  Autotests/test_freeciv_rulesets.py \
  Autotests/test_freeciv_oracle.py \
  Autotests/test_freeciv_beliefs.py \
  Autotests/test_freeciv_planning.py \
  Autotests/test_freeciv_pressure.py \
  Autotests/test_freeciv_pressure_v2.py
python3 scripts/run_fdas_phase0_baseline.py --check --iterations 1
```

## Activation state

```text
city_domain_projection = component-only
typed city/economy groundings = component-only
local goal/candidate construction = component-only
dependent_atom_pressure_adapter = not-built
operation_atom_projection = not-built
component_enabled = true
policy_authority = false
```
