# PR50 path-persistence delayed-relevance discovery

## Decision

PR50 finds **no incremental delayed-relevance advantage** for persistence-only
corridors over deterministic matched near-tied controls. Source--sink flow
therefore remains closed: PR49 established additional temporal membership, but
PR50 does not show that this membership preferentially retains the more useful
candidate.

This is a post-hoc exploratory analysis of the already inspected PR49 cohort.
It is not a preregistered confirmation and supports no causal candidate-value,
gameplay, score, or win-rate claim.

## Method

For each game's first persistence-only addition of a unique stable corridor:

1. select a within-decision control that is also outside the probe union;
2. prefer the same operation type;
3. then minimize instantaneous-reachability distance, scalar-rank distance,
   and stable route identity in that order;
4. follow both routes for eight subsequent candidate decisions; and
5. record whether each route enters the probe union or becomes the scalar
   winner before expiry or horizon censoring.

The evaluator uses only the frozen shadow event stream. It does not treat an
unexecuted candidate as having a realized transition or goal-relief outcome.
The eight-decision window was selected during discovery after descriptive
inspection and therefore cannot be treated as confirmatory.

## Results

The 105 temporal additions in PR49 represented 30 first unique treatment
routes. Seventeen had a valid non-probe matched control; 13 did not, for matched
coverage of `56.7%`. Fifteen pairs had uncensored outcomes for each endpoint.

| Endpoint within 8 decisions | Persistence | Control | Paired delta | Positive/negative discordance | Exact two-sided sign p |
|---|---:|---:|---:|---:|---:|
| probe re-entry | 12/15 | 13/15 | -0.0667 | 1 / 2 | 1.0 |
| future scalar winner | 10/15 | 11/15 | -0.0667 | 3 / 4 | 1.0 |

The high absolute rates show that persistence operates on recurrent near-tied
corridors. The matched comparison shows that the persistence signal did not
identify future relevance better than a nearby non-probe candidate in this
discovery sample. The small matched sample and incomplete coverage make the
estimate imprecise, but neither endpoint has the positive direction required
to justify confirmation or a more expensive flow layer.

The canonical exploratory report is
`docs/freeciv/evidence/fdas-pr50-path-persistence-relevance-discovery.json`,
with report hash
`259c2f4aceb56be609935e306ae55a1e96edbec843eab83b5038cc7f99233238`.

## Claim boundary

PR50 measures future rank/probe relevance, not realized candidate value. A
route can become the later scalar winner and still be a poor action because
the frozen scalar transition estimate itself can be wrong. Conversely, a
useful unexecuted alternative may expire without an authoritative outcome.

Accordingly, PR50 does not reverse the PR49 mechanism claim, but it blocks the
inference that more temporal recall should improve decisions. It also gives no
basis for fluid transport, capacity duals, advection, or temporal ranking
authority.

## Next scientific requirement

The remaining bottleneck is the same decision-safe readout problem identified
before the FDAS membership sequence: authoritative realized goal relief exists
only for executed candidates. A meaningful next program must collect safe,
propensity-recorded alternative-action outcomes or identify another valid
counterfactual design, calibrate by action category and lifecycle state, and
freeze candidate-value evaluation before granting any ranking authority.

Do not use source--sink flow to compensate for this missing value label. Flow
may be reconsidered only after replay identifies a residual error specifically
caused by route/capacity allocation beyond the exact scheduler, and after its
controller-inclusive expected value exceeds latency cost.
