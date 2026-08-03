# PR57 execution hardening replay preregistration

Status: preregistered; execution not started

## Purpose and claim boundary

PR57 is a claim-ineligible engineering replay of the two exact PR56 failure
seeds. It tests only the corrections for two engine-rejection paths discovered
by the fixed PR56 cohort:

1. seed `106417` received proxy-advertised spatial actions outside a
   non-wrapping 26 by 26 map and selected `unit_move` to `(10,-1)`; and
2. seed `107123` accepted a randomized unit move without a subsequent source
   sequence update, then reprojected and submitted the same treatment action
   again from the stale snapshot after the actor's movement was consumed.

Both seeds and defects are known, so PR57 cannot contribute to opportunity
yield, candidate value, gameplay, score, or win-rate estimation. Outcome
direction is irrelevant to every progression decision.

## Frozen implementation

- canonical legal-action ingestion removes every spatial action whose exact
  executable coordinates are outside the authoritative map dimensions,
  including on wrapping maps where submitted coordinates must still be
  canonical;
- an accepted unit action that does not cross the bounded authoritative source
  sequence barrier ends the current action phase, preventing FDAS authority or
  the legacy planner from using the stale legal-action digest again;
- both guards are fail-closed and leave pressure, truth, assignment,
  propensity, outcome, and final execution-gate semantics unchanged; and
- `decision_stale_unit_scope_followups_blocked` records the new stale-unit
  boundary independently of the narrower terminal-actor counter.

The focused state, harness, and Impact suite passes 294 tests before this
preregistration.

## Frozen execution

| Input | Value |
|---|---|
| Config | `profile/freeciv_harness_fdas_pr57_execution_hardening_replay_160_turn.yaml` |
| Executed seeds | `106417`, `107123` |
| Config fillers | 28 inert validation-only seeds |
| Horizon | 160 turns or audit-1.5 terminal-absorbing endpoint |
| Backend | `engine-live` |
| Condition | `e_full_loop` only |
| Workers | 2 on ports 6001 and 6002 |
| FDAS manifest | `profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json` |
| Audit | `fdas-randomized-alternative-live-audit/1.5` plus defect-specific trace checks |
| Output | `artifacts/freeciv/fdas-pr57-execution-hardening-replay-v1` |

The launch must use a clean committed descendant containing this
preregistration, `--limit-seeds 2`, `--main-only`, and `--no-resume`. The
remaining seed entries only satisfy the harness's minimum configuration size
and are excluded by the frozen prefix limit.

## Acceptance criteria

PR57 passes only if:

1. both games reach the fixed or terminal-absorbing endpoint with no
   infrastructure failure and zero rejected actions;
2. every emitted spatial legal action is within the current authoritative map
   dimensions, including seed `106417` at the historical turn-135 boundary;
3. no snapshot/action pair is submitted twice after an accepted unit action;
4. if a unit action times out its authoritative refresh, the stale-unit guard
   increments and no later unit action is sent from that unchanged snapshot;
5. every randomized assignment that occurs retains exact draw, propensity,
   action, episode, selected-choice, and due-label linkage;
6. event ledgers and stores validate without warning or quarantine; and
7. no truth, claim, score, flow, advection, capacity, or unrelated action
   authority is introduced.

A pass proves only the two mechanics corrections. PR56 remains invalid and
cannot be repaired by this replay.
