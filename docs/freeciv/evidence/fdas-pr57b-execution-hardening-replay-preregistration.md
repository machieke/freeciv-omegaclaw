# PR57b execution hardening replay environment correction

Status: completed safely; randomized-profile audit rejected

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

## Launch result

PR57b ran both seeds from clean commit `9e1624c`, reached the fixed endpoint,
and recorded zero infrastructure failures, rejected actions, or resumes. It
therefore supplies supporting evidence for the general action-ingestion guard.

The standard randomized audit nevertheless rejects both games before lifecycle
analysis because their manifests identify `profile/fdas_manifest.json`, not the
intended randomized-alternative manifest. The prior shell environment had also
provided `FREECIV_FDAS_CONFIG_PATH` and `FREECIV_FDAS_MANIFEST_PATH`; PR57b
corrected only the first missing variable it encountered and therefore ran the
default FDAS profile with zero randomized assignments. The rejected machine
report is `fdas-pr57b-execution-hardening-replay.json`, report hash
`9bda0fb0501051ac71fc1d8358dd56a7c0646efa46351261eee120f1c0983e65`.

PR57c removes this ambient dependency by declaring both intended FDAS paths in
the harness YAML itself. No controller value, seed, horizon, or acceptance
criterion changes. See
`fdas-pr57c-execution-hardening-replay-preregistration.md`.
