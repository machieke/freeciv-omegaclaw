# FDAS PR30 promoted-rule consolidation

Status: clean-source retrospective audit accepted; 13 held-out-approved rules
reduce to a four-rule diagnostic basis; induced-rule readout remains disabled;
no gameplay or score claim.

## Purpose and boundary

PR29 found 13 syntactically distinct rules, but several conjunctions used the
same training population and emitted exactly the same calibrated prediction as
an approved simpler rule. PR30 adds a deterministic structural-subsumption
contract before any readout experiment.

The consolidator requires one matching promoted validation and versioned
approval for every input. It then uses training-artifact fields only. A rule is
suppressed exactly when:

1. an already retained rule has the same context and consequent;
2. its antecedents are a strict subset of the candidate's antecedents; and
3. training population, provenance, support, positive count, calibrated
   probability, baseline, residual, generalization, source, and transfer
   uncertainty are identical.

Validation outcomes and held-out metrics are deliberately absent from this
comparison. Differently calibrated conjunctions, incomparable rules, rules
from another context, and rules from another training sample remain distinct.
Input order cannot change the result.

## Frozen PR29 result

The clean runner at commit `7a8db90bf8052efb5b8e334e644799c6eb99e08e`
consumed the hash-verified PR29 report and produced:

| Measure | Count |
|---|---:|
| Approved input rules | 13 |
| Retained diagnostic rules | 4 |
| Structurally suppressed rules | 9 |

The retained basis is:

| Antecedent | Training support | Positive | Smoothed probability |
|---|---:|---:|---:|
| City production class is `unit` | 15 | 12 | 0.76471 |
| City size band is `2-4` | 9 | 8 | 0.81818 |
| Unit production and no visible near-city enemy | 12 | 10 | 0.78571 |
| Positive operating gold and no visible near-city enemy | 15 | 12 | 0.76471 |

Five city-size conjunctions reduce to the city-size singleton. Four
unit-production conjunctions reduce to the unit-production singleton. The
unit-production/no-visible-enemy conjunction remains because its calibrated
probability differs. Positive-gold/no-visible-enemy remains because neither
of its singleton antecedents was approved, so no retained strict subset
exists.

## Safety and interpretation

All input promotions remain bound to the exact PR29 training and confirmation
artifacts. The consolidation partitions every approved input exactly once and
reports an explicit retained-rule and removed-antecedent witness for every
suppression. Truth mutation, policy authority, and readout authority are all
false.

This policy was designed after inspecting the PR29 result. Its application to
PR29 is therefore a retrospective mechanics audit, not independent validation
of the policy. The four retained rules are not four independent causal effects,
and this result does not establish decision value. A fresh, preregistered
shadow-readout cohort is required before any candidate-selection, gameplay,
score, or win-rate claim.

The machine-readable artifact is
[`fdas-pr30-promoted-rule-consolidation.json`](fdas-pr30-promoted-rule-consolidation.json).
Its structural hash is
`1b9ace13af86dddc0afeb4161de5a68e0d239a38955f0ea538f82889d6926dc8`;
the consolidation-result hash is
`aa9aceb49077fc8ed35c4eda06a30074ecafb62dc2ec51e24c8a2de18d56cd9c`.
