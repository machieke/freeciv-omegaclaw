# FDAS Phase 9 episode/control-learning bridge evidence

Status: component-only, shadow-only, no policy authority.

Decision episodes now distinguish an accepted action, no observed effect,
immediate effect, effect without eventual goal relief, delayed pending state,
and authoritative goal relief. Pending episodes are indexed by persistent
operation identity so a later observation can resolve the exact episode after
the original decision turn.

`FdasEpisodeLearningAdapter` consumes only three attributable terminal states:

- goal relief credits the exact contextual route;
- a closed no-effect window applies bounded no-progress decay;
- an observed effect without goal relief remains a successful transition but
  also applies no-progress conductance decay.

Confounded, contradicted, unresolved, and pending outcomes abstain. Each sample
requires exactly one prediction ID bound to the same operation. The prediction
supplies the route, calibration group, predicted relief/success/cost,
selection propensity, frontier, and lifecycle generation. The resulting
`ControlCalibrationRecord` carries a unique episode-specific authoritative
relief source while its route key remains context-qualified for aggregation.

Replay is idempotent: the calibration ledger and contextual conductance store
recognize the same immutable episode record, and a duplicate reports no
applied update. The adapter exposes `truth_mutated=false` and
`policy_authority=false`; it has no reference to a belief store, AtomSpace
transaction, action binding, or execution path.

Coverage is in `Autotests/test_freeciv_fdas_episodes.py` and
`Autotests/test_freeciv_fdas_episode_learning.py`.

The calibration record now retains the immutable episode ID. Read-only
`metrics()` reports episode outcome counts, attributable/confounded totals,
calibration samples, exact route-context count, mean absolute relief error,
success Brier score, and the deterministic conductance state hash.
`explain(episode_id)` exposes the linked prediction, calibration record,
current context-qualified conductance, eligibility, and abstention reason.
Neither diagnostic method applies a sample or changes truth, conductance, or
policy authority.
