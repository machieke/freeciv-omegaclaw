# GDO-7C grounded city-worker macro

## Result

GDO-7C passes its shadow-only mechanism gate on retained, player-visible
FreeCiv engine snapshots. The implementation preserves the authoritative
solver boundary: pressure chooses one city, a bounded food/happiness
constraint, and one optimization-budget allocation; the advertised
`city_governor` macro delegates tile and specialist assignment to FreeCiv's
server-side citizen manager.

The replay covers 9 retained `city_governor` candidates. The immediate simpler
candidate projection exposes no complete output vector. The grounded model
exposes all 9 current output vectors as typed `produced`, `used`, and `net`
food, shield, trade, gold, luxury, and science values. It emits no individual
citizen actions and makes no pre-execution output point estimate.

One selected macro has an adjacent authoritative snapshot that confirms the
requested configuration and constraint:

- turn 132: city 127 advertises a food-surplus minimum of 1, with net food 0
  and the governor disabled;
- turn 133: the governor is enabled with minimum surplus
  `[1, 0, 0, 0, 0, 0]`, and observed net food is 1.

A second adjacent selected action is retained, but the requested configuration
is not visible in its next snapshot. It is reported as
`configuration-not-observed`, not converted into success or failure.

## Contract

- `GroundedCityWorkerTransitionModel` admits only an owned city, an advertised
  legal macro, an authoritative governor capability, bounded constraints, and
  a complete current output vector.
- Macro submission has no immediate goal-relief claim. A later authoritative
  snapshot is the result source.
- `CityWorkerMacroAssembler` creates one operation step, one identity-bearing
  city-worker-assignment claim, one action-budget claim, and a complete
  `RequirementSet`.
- Citizen assignments remain invisible through this protocol. No per-citizen
  action is synthesized.
- The server interface does not expose a pre-execution `cm_result` or solver
  bound. Predicted output and optimality gap therefore remain explicitly
  unavailable.
- The runtime layer is default off, shadow only, and requires domain estimates,
  commit revalidation, identity resources, the resource scheduler, operation
  lifecycle, and RequirementSets.

## Reproduction

```sh
python3 scripts/run_gdo_city_worker_replay.py
python3 -m pytest -q \
  Autotests/test_freeciv_city_worker_macro.py \
  Autotests/test_freeciv_pf_runtime.py \
  Autotests/test_freeciv_operations.py \
  Autotests/test_freeciv_pressure_v2.py::test_v1_golden_artifacts_remain_byte_exact_in_compatibility_mode
```

The canonical diagnostic is
`benchmarks/gdo/gdo7c_city_worker_macro_diagnostic.json`. It records fixture
hashes, per-candidate semantic results, adjacent observed outcomes,
repeatability, latency, and the mechanism gates.

## Claim boundary

This is an engine-backed semantic and observability mechanism result. The
retained capture set does not expose the full legal action set for every
fixture, does not measure the citizen-manager optimality gap, and is not a
randomized policy evaluation. It grants no live policy authority and makes no
score or win-rate claim.
