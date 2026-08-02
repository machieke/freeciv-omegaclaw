# FDAS PR29 causal induction held-out confirmation

Status: strict clean-source confirmation accepted; 13 of 32 frozen proposals
passed held-out replay and received artifact-bound approvals; induced-rule
readout remains disabled; no score or gameplay claim.

## Frozen train/holdout boundary

The PR28 proposal freeze was trained on seeds `104831`, `104849`, and
`104851`. Confirmation used the preregistered next untouched seeds `104869`,
`104879`, and `104891`. All six games completed the fixed 160-turn horizon
from clean sources with the same implementation hash and exact
`defense-episode-features/3.0` activation. Every event ledger and delayed-label
audit passed.

| Partition | Seeds | Resolved | Positive | Negative |
|---|---|---:|---:|---:|
| Discovery | 104831, 104849, 104851 | 19 | 14 | 5 |
| Confirmation | 104869, 104879, 104891 | 14 | 11 | 3 |

The complete confirmation cohort was collected before validation. The held-out
runner reproduced all 32 committed PR28 proposal records and IDs exactly.

## Verdicts

Thirteen proposals passed the unchanged replay gates, 16 were demoted for no
out-of-sample improvement, and three were demoted for fewer than four held-out
activations. Every promotion has a versioned approval bound to the exact
training artifact, confirmation artifact, proposal, validation, and ledger.

The 13 passing syntactic rules form four distinct held-out activation sets:

| Family | Passing rules | Holdout activations | Held-out outcomes | Brier improvement | Calibration improvement |
|---|---:|---:|---:|---:|---:|
| City size `2-4`, alone or conjoined | 6 | 5 | 5 positive / 0 negative | +0.01735 | +0.10390 |
| Unit production, alone or mostly conjoined | 5 | 11 | 9 positive / 2 negative | +0.00623 to +0.00765 | +0.05042 to +0.07143 |
| Unit production + positive operating gold | 1 | 9 | 8 positive / 1 negative | +0.00968 | +0.05042 |
| Positive operating gold + no visible near-city enemy | 1 | 11 | 9 positive / 2 negative | +0.00623 | +0.05042 |

The most useful result is semantic transfer, not the raw count of 13. Exact
unit type—the feature that failed PR26—is absent from the new miner. The
single-feature city-size and production-class rules both generalize to
untouched engine games. Conversely, the large-city (`5-8`) association and
empire-size (`3+`) association fail out of sample and remain demoted.

Several passing conjunctions were constant or activation-equivalent in this
small cohort. They are valid replay promotions under the frozen gate but should
not be treated as 13 independent discoveries. Any future readout must use a
separate decision-safe redundancy/subsumption policy and a new safety/gameplay
experiment; this holdout must not be reused to design or validate that policy.

## Authority and claim boundary

The machine-readable report is
[`fdas-pr29-causal-induction-holdout-engine.json`](fdas-pr29-causal-induction-holdout-engine.json).
Its structural hash is
`3793db47ed8aa058d78d28ff68d621fafebcc1de4b7504bf3395ac8d66c10a37`.
All source, horizon, partition, label, proposal, validation, approval,
persistence, and safety checks pass.

This establishes held-out predictive utility for a narrow 32-turn attributed-
defender persistence target. It does not establish causal intervention value,
authorize any action, change a legacy winner, or support a score/win-rate
claim. Truth mutation, policy authority, and induced-rule readout are all
false.
