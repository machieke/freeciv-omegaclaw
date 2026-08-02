# FDAS PR28 causal induction discovery freeze

Status: clean engine discovery accepted; 32 proposals frozen in quarantine;
held-out validation pending; no promotion, readout, score, or gameplay claim.

## Fresh discovery cohort

The first `defense-episode-features/3.0` discovery cohort used the next three
previously untouched pinned seeds: `104831`, `104849`, and `104851`. All three
completed the fixed 160-turn horizon from clean commit `6b86fb5c`; their event
ledgers validate without errors or warnings and their delayed-label audits
accept the exact schema/activation match.

| Seed | Resolved labels | Positive | Negative |
|---:|---:|---:|---:|
| 104831 | 4 | 4 | 0 |
| 104849 | 5 | 5 | 0 |
| 104851 | 10 | 5 | 5 |
| **Total** | **19** | **14** | **5** |

The full cohort was collected before mining. Contrast came from the third
preregistered seed; there was no seed selection or outcome-dependent stopping.

## Frozen proposals

The clean-source discovery runner at commit `16f089d5` encoded all 19 labels
and mined with the predeclared bounds: minimum support `4`, maximum antecedents
`2`, minimum residual `0.05`, and maximum candidates `32`. It reached the
candidate cap: four single-feature and 28 two-feature proposals were written to
a hash-bound quarantine ledger. There are no validations, approvals, or
promotions in a discovery artifact.

The strongest single-feature association was `city_size_band=5-8`: support
`6`, two positives, smoothed probability `0.3750` versus the `0.7143`
population baseline. Other single-feature candidates cover city size `2-4`,
empire size `3+`, and unit production. Numerous conjunctions share identical
training activations because several context values were constant in this
small population. They remain frozen rather than being pruned after inspecting
discovery outcomes; held-out activations and calibration decide their fate.

The machine-readable proposal freeze is
[`fdas-pr28-causal-induction-discovery-engine.json`](fdas-pr28-causal-induction-discovery-engine.json).
Its structural hash is
`dd223793c73f4651f5bacfdabbbd29bbd05833c516fdf06f43ca635e4456dc81`
and the quarantine ledger state hash is
`082e54aa3d5a3dc6dc4d3442cfd8f83b556b2caf68e4d693ba68d7b089611d16`.

## Confirmation boundary

The proposal JSON, target, schema, training stores, label stores, and mining
thresholds are frozen before confirmation collection. The next untouched
pinned seeds are preregistered as `104869`, `104879`, and `104891`. They form
one complete confirmation cohort; collection will not stop when a sample or
outcome threshold is crossed. The existing replay validator retains minimum
`8` total samples, minimum `4` activations per rule, positive Brier and
calibration improvement, and no increased contradiction rate.

Even a held-out promotion would establish only predictive utility for the
versioned delayed target. It would not grant live induced-rule readout or imply
a score or win-rate improvement.
