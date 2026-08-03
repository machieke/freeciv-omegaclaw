# PR57c explicit-profile execution hardening replay

Status: preregistered; execution not started

Implementation commit: `b6248222eb1baed3847448f90d651c882f29cadf`

## Correction boundary

PR57b completed safely but used the default FDAS declaration because the
intended config and randomized manifest existed only as ambient shell
overrides. PR57c extends the strict seed overlay format to permit only an exact
`dependent_atomspace` path pair, then makes those already-preregistered inputs explicit in
`profile/freeciv_harness_fdas_pr57_execution_hardening_replay_160_turn.yaml`:

```yaml
dependent_atomspace:
  config_path: profile/dependent_atomspace_defense_choice_surface_shadow.yaml
  manifest_path: profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json
```

This is a launch-reproducibility correction, not a controller or intervention
change. The executed seeds remain `106417` and `107123`; the remaining 28 are
validation-only fillers. Horizon, workers, ports, assignment policy, outcome
target, code, and all PR57 acceptance criteria remain frozen. The only required
ambient binding is the pinned local `FREECIV_RULESET_ROOT`.

The run starts from scratch with `--no-resume` and writes
`artifacts/freeciv/fdas-pr57c-execution-hardening-replay-v1`. PR57 and PR57b
artifacts remain immutable. This exact known-seed replay is permanently
claim-ineligible.
