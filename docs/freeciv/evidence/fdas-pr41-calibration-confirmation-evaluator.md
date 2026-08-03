# FDAS PR41 calibration confirmation evaluator

PR41 implements the evaluator required before the reserved confirmation seeds
may be touched. It loads and hash-checks the frozen discovery artifact, rejects
discovery/confirmation store overlap, reruns the complete engine-yield audit,
and evaluates only observed selected actions. Censored alternatives remain
unlabeled and outside every metric.

Repeated route-step rows collapse to one durable lineage observation. Metrics
are reported overall and separately for move and fortify strata: prediction
coverage, Brier score, log loss, calibration in the large, and whether the
predicted mean lies inside the held-out empirical Wilson interval. Lifecycle
conditioning is compared with the frozen action-only estimate using a
deterministic game-clustered bootstrap, so rows from one game cannot claim
independence.

The evaluator grants no truth, readout, or policy authority. It fails closed
on model-hash mismatch, source overlap, missing lineage/game provenance,
cross-source lineage identity, incomplete action support, insufficient engine
yield, invalid thresholds, or any frozen predictive gate. Forty-two focused
calibration, validation, episode, and choice tests pass.

This is evaluator implementation only. Confirmation seeds remain untouched,
and no out-of-sample calibration or ranking claim exists yet.
