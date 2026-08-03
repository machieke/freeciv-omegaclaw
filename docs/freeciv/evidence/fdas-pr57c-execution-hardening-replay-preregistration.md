# PR57c explicit-profile execution hardening replay

Status: completed; all frozen engineering gates passed

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

## Result

PR57c ran both seeds from clean commit `1091c93`, reached turn 161 in both
games, and recorded zero infrastructure failures, rejected engine actions, or
resumes. Both manifests bind the intended randomized profile and exact FDAS
configuration. Randomized audit 1.5 passes every source, manifest, endpoint,
ledger, store, linkage, treatment, reprojection, and counter gate. It found 17
fully resolved assignments in seed `107123` (7 control and 10 treatment) and
none in seed `106417`; these known-seed outcomes remain claim-ineligible.

The independent trace audit checked 640 snapshots, 86,166 spatial legal
actions, and 640 accepted action submissions. It found no off-map spatial
action, no accepted snapshot/action pair submitted twice, and no later unit
action after an accepted unit action on the same snapshot. At the historical
seed-`106417` turn-135 boundary, all 142 spatial actions were within the 26 by
26 canonical map. The seed-`107123` run performed three valid authority catalog
reprojections without replay or rejection. Its refresh timeout did not recur,
so the live stale-unit guard counter remained zero; the conditional guard path
continues to be covered by the focused regression suite rather than claimed as
fresh live branch coverage.

Evidence:

- `fdas-pr57c-execution-hardening-replay.json`, randomized audit report hash
  `f5894d6bb299eaac4543c0cc834ca207893983d993b576242ec3a8ae23733a6e`;
- `fdas-pr57c-execution-hardening-trace.json`, trace audit report hash
  `f5183c0c90765b8986747d022a7f8ea02ac2edc5e42e3d8a4fd040d93be92b89`.

PR57c therefore passes its frozen claim-ineligible engineering acceptance
criteria. It does not repair PR56, support a candidate-value claim, or justify
repeating the adverse bounded-nearest-score intervention.
