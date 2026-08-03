# PR57b execution hardening replay environment correction

Status: preregistered; execution not started

Implementation commit: `b6248222eb1baed3847448f90d651c882f29cadf`

## Correction boundary

PR57 stopped before gameplay because its shell omitted
`FREECIV_RULESET_ROOT`. PR57b changes only that local environment binding:

```text
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data
```

The path contains the pinned `civ2civ3` ruleset used by the preceding live
cohorts. Code, source commit lineage, two executed seeds, filler seeds, horizon,
workers, ports, FDAS configuration and manifest, randomization policy, outcome
target, claim boundary, and every PR57 acceptance criterion remain unchanged.

The run starts from scratch with `--no-resume` and writes
`artifacts/freeciv/fdas-pr57b-execution-hardening-replay-v1`. The failed PR57
artifact remains immutable. This known-seed replay is permanently
claim-ineligible regardless of outcome direction.
