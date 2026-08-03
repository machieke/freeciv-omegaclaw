# PR58 calibrated and grounded decision-safe candidate readout

Status: implemented and unit-tested; clean engine smoke not started

## Purpose

PR56 showed that consistently routing compute to a bounded nearest-score
alternative is not enough. Its descriptive treatment direction was adverse,
and two execution failures made the cohort mechanically invalid. PR57c closes
those execution defects but deliberately does not repair or repeat the value
intervention.

PR58 addresses the semantic failure as a separate, shadow-only component. It
does not retune scalar PF-v2, packets, probes, persistence, pressure,
conductance, or any action priority. It asks a narrower question: does a
candidate have calibrated evidence that clears the active control candidate's
uncertainty interval, while remaining no worse on exact authoritative
reinforcement mechanics?

## Frozen readout contract

The readout consumes the existing PR40/PR42 action- and lifecycle-stratified
calibration model, the revision-current candidate union, the exact active
legacy action, current FDAS supports, and authoritative native movement-route
and unit facts. A counterfactual preference is emitted only when all of the
following hold:

1. the active action is an exact `unit_move` with one unique FDAS
   city-garrison route;
2. control and alternative predictions are calibrated and eligible under the
   existing maximum-width gate;
3. the alternative lower confidence bound is strictly above the control upper
   confidence bound plus the configured non-negative separation margin;
4. both candidates pass the bounded reinforcement validator, including the
   source-garrison opportunity-cost guard;
5. action stratum, target city, unit type, and current resource isolation
   match; and
6. authoritative route ETA, total and first-step movement cost, hit points,
   moves left, veteran level, and target-home-city relation are all
   non-inferior to control.

Any missing grounding, interval overlap, target mismatch, source risk, or
mechanical regression produces an explicit abstention and why-not reason. The
component records `counterfactual_change` only as a diagnostic. Its event
contract requires `action_selection_changed`, `policy_authority`,
`readout_authority`, and `truth_mutated` all to remain false.

## Implementation

- `planning/fdas_decision_safe_candidate_readout.py` defines the typed config,
  grounded candidate values, hashed readout, and fail-closed evaluator.
- The engine manifest loader requires the calibrated candidate union and an
  exact canonical declaration before enabling the component.
- Runtime events are revision-bound under
  `fdas-decision-safe-candidate-readout/1.0`.
- Aggregate, terminal, and status counters distinguish evaluations, eligible
  shadow preferences, abstentions, and counterfactual changes.
- `profile/fdas_manifest_defense_decision_safe_readout_shadow.json` is the only
  activating manifest. It cannot grant policy or readout authority.
- `profile/freeciv_harness_fdas_pr58_decision_safe_readout_160_turn.yaml`
  binds the exact FDAS config and manifest rather than relying on ambient
  environment paths.

Unit coverage proves a separated, mechanically equal alternative is exposed
only as a shadow preference; overlapping intervals abstain; and an otherwise
superior estimate with a worse native ETA/cost also abstains. The existing
alternative-collection and harness tests remain the compatibility boundary.

## Clean engine smoke

The first post-commit execution will run unseen seed `108013` for 160 turns
with `--limit-seeds 1`, `--condition e_full_loop`, `--main-only`, and
`--no-resume`. The only required ambient value is the pinned local
`FREECIV_RULESET_ROOT`. Output will be written to
`artifacts/freeciv/fdas-pr58-decision-safe-readout-smoke-v1`.

The smoke passes only if:

- the game reaches its fixed or genuine absorbing terminal endpoint with zero
  infrastructure failures and rejected actions;
- the exact clean source, explicit config, and PR58 manifest are recorded;
- every decision-safe event is revision-current, hash-valid, and paired with
  its calibrated-union parent;
- event counts equal status and metric counters;
- every eligible preference satisfies interval separation and all grounded
  non-inferiority checks;
- every non-eligible evaluation is an explicit abstention; and
- no PR58 event changes an action or grants truth, policy, readout, flow,
  packet, or resource authority.

Eligibility is not required for this one-game mechanics smoke: honest
abstention is the expected result when the frozen model cannot separate the
pair. A later unseen-seed yield design may proceed only if the smoke is clean.
No randomized intervention, candidate-value, gameplay, score, or win-rate
claim is permitted by PR58.
