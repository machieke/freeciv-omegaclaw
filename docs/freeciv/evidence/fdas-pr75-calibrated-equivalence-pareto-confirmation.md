# FDAS PR75 calibrated-equivalence Pareto confirmation

Date: 2026-08-03
Runtime source: `5655a56`
Audit report: `fdas-pr75-calibrated-equivalence-pareto-confirmation.json`
Report hash: `9ee9259902f341e630a23c945a6791781ac4f9506f057ebe613f837b05df05ae`

## Result

The preregistered known-opportunity confirmation passes all five gates. Seed
`109433` completed through observed turn 161 with 461 accepted engine actions,
zero rejected actions, a valid event ledger, matching runtime counters, and a
clean frozen source identity. All 137 scalar readouts used only version `1.2`.

The run produced 47 grounded same-target alternatives. Nineteen carried at
least one strict grounded improvement. Thirteen satisfied exact calibration
equivalence and full grounded noninferiority and therefore emitted shadow
preferences. No independently interval-separated preference occurred. The
remaining 34 alternatives retained ordinary interval-overlap abstention.

Every preference was explicitly non-authorizing: `action_selection_changed`,
`policy_authority`, `readout_authority`, and `truth_mutated` remained false,
and the inherited filter, target, union, counter, endpoint, and rejection gates
all passed.

## Observed pattern

The first preference appeared at turn 133. Riflemen actor 170 was the scalar
control at ETA 3 and movement cost 18; Riflemen actor 175 was the protected
alternative at ETA 2 and cost 12. Both had the identical action-backoff
estimate `0.476009`, interval `[0.261651, 0.690368]`, 17 effective lineages,
and the same grounded unit/capability facts. The alternative passed every
noninferiority check and was strictly better on ETA and total movement cost.

Subsequent preferences followed the same exact contract, sometimes with a
two-turn or twelve-cost route advantage. The readout did not manufacture
statistical superiority: it labeled the marginal calibration as exactly
equivalent and used only strict grounded Pareto dominance to distinguish the
candidates.

## Interpretation and boundary

PR75 proves that readout `1.2` can recover mechanically meaningful choice
signal that the broad marginal intervals necessarily suppress, without
weakening any inferior-dimension or authority guard. It remains known-seed
integration evidence. A fresh unseen-seed cohort is required to estimate
preference yield before any randomized outcome or bounded-authority proposal.

This result establishes no counterfactual ranking quality, treatment effect,
gameplay impact, score improvement, or win rate and grants no action authority.
