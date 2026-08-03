# PR52e selection-indexed randomized execution pilot preregistration

Status: executed; mechanically rejected on treatment exercise

Corrected implementation commit: `6774edd`

## Purpose and claim boundary

PR52e repeats the claim-ineligible PR52 mechanics pilot after correcting the
delayed-label completeness defect found in PR52d. It may establish only that a
randomly assigned alternative is selected, executed, episode-linked, and given
a complete delayed outcome lifecycle even when its first effect provides no
immediate goal relief. It cannot support candidate value, gameplay, score, or
win-rate claims and will never enter causal fitting or performance evaluation.

## Frozen inputs

All PR52d gameplay and assignment inputs remain unchanged:

| Input | Value |
|---|---|
| Engine seed | `105491` |
| Horizon | 160 turns |
| Backend | `engine-live` |
| FDAS config | `profile/dependent_atomspace_defense_choice_surface_shadow.yaml` |
| FDAS manifest | `profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json` |
| Experiment ID | `fdas-reinforcement-randomized-execution-pilot-v1` |
| Assignment seed | `2` |
| Treatment probability | `0.5` |
| Action slice | `unit_move` / `city_garrison_move` |
| Alternative source | bounded nearest score |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |
| Frozen output | `artifacts/freeciv/fdas-randomized-execution-pilot-v1-selection-indexed` |

The seed remains deliberately targeted from prior observed mechanics and is
therefore scientifically claim-ineligible.

## Mechanical acceptance criteria

The ten original PR52 criteria remain binding. Criterion 9 is made explicit:

- every accepted selected in-scope action opens exactly one selected-actor
  label at its accepted action turn, independent of immediate goal relief;
- the label's index revision equals the episode's before revision and its due
  turn is exactly 32 turns after selection;
- the label is observed at or after its due turn, or remains durably pending
  only when the fixed horizon precedes that due turn;
- the selected choice set resolves from that exact label when observed;
- no rejected or nonselected action receives a label.

The retry also requires a clean source at commit `6774edd`, valid event/store
hashes, zero rejected engine actions, one causal chain from assignment through
label observation, and no truth, claim, flow, advection, capacity, or unrelated
policy authority.

## Safety stops and decision rule

Stop and reject on any stale or mismatched revision, assignment, action,
episode, label, choice set, actor, due turn, propensity, or causal parent; on
any action rejection or infrastructure failure; or on any authority outside
the exact bounded randomized assignment.

If PR52e passes, it confirms mechanics and opportunity yield only. A larger
randomized collection cohort still requires a separately frozen design with
fresh game and assignment seeds, clustered uncertainty, effective-sample-size
gates, and no reuse of any PR51/PR52 pilot outcome.

## Frozen outcome

PR52e completed the fixed horizon with 406 accepted and zero rejected engine
actions. It fully validates the corrected outcome lifecycle. The accepted
randomized episode opened its selected-actor label at selection turn 17 with
index revision equal to the episode before revision and due turn 49. The label
was observed at turn 49 as negative (`selected-actor-not-at-city-at-due-turn`),
and the exact candidate choice set resolved from that label. Across the game,
16 labels opened, 12 were observed, and four remained validly pending beyond
the horizon.

PR52e fails original criterion 4 because the sole eligible assignment selected
control, so no treatment action changed the legacy winner. RCA found that the
old assignment key included FDAS revision, snapshot, persistence-union, and
operation hashes. Adding selection-indexed episode provenance legitimately
changed those bookkeeping identities and therefore changed the pseudorandom
draw. That makes assignment sensitive to non-policy instrumentation and is not
acceptable for a randomized cohort. The artifact is preserved unchanged at
the frozen output and remains excluded from fitting and claims.

Commit `1a14afd` replaces that key with an exogenous game-turn exact-action-pair
unit containing only game, turn, control and treatment action keys, experiment,
policy version, and seed. Tests verify that changing operation, pressure,
packet, or commit hashes cannot alter assignment.
