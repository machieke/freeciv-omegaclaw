# PF-PLN fifth-city confirmation v1

Status: complete; predeclared turn-60 score-improvement claim supported

The claim-eligible `expansion_fifth_city_confirmatory_v1` cohort completed all
100 fresh pairs and 200 current engine arms. Both arms used adapter 1.17,
deadline recovery, packet-grounded site preference, pressure, conductance
learning, score alignment, disabled optional escort policies, and a 15-turn
post-settlement runway. The only arm difference was
`expansion_city_target`: four under baseline and five under treatment.

## Confirmed outcome

Mean turn-60 score increased from 119.38 to 120.94. The paired difference was
**+1.56**, with 95% paired-bootstrap interval **[+0.88, +2.23]** and exact
two-sided paired sign-flip **p=1.998e-5**. Both predeclared score-superiority
gates passed, so the own-score improvement is supported.

The separate ten-pair diagnostic estimated `+1.1` `[+0.1, +2.1]`, and the
separate 40-pair pilot estimated `+1.675` `[+0.725, +2.575]`. Neither was
pooled with confirmation. Fifty-six confirmation pairs improved, 18 tied,
and 26 declined; total paired score increased by 156 points.

| Outcome | Baseline | Treatment | Paired delta | 95% interval |
|---|---:|---:|---:|---:|
| Total score | 119.38 | 120.94 | +1.56 | [+0.88, +2.23] |
| Citizen component | 14.54 | 16.14 | +1.60 | [+1.09, +2.11] |
| Technology component | 102.44 | 102.44 | 0.00 | [-0.12, +0.10] |
| Residual component | 2.40 | 2.36 | -0.04 | [-0.32, +0.25] |
| Score margin | -7.91 | -6.86 | +1.05 | [-0.91, +3.10] |
| Opponent score | 127.29 | 127.80 | +0.51 | [-1.07, +2.11] |

The effect is not supported as strictly greater than two points: the estimate
is 1.56, the interval includes values below two, and the predeclared
greater-than-two exact test has `p=0.9014`.

Fixed-horizon score-lead rate changed from 26% to 27%, a paired `+0.01` with
interval `[-0.07, +0.08]`. Eight pairs led only under treatment, seven only
under baseline, 19 in both arms, and 66 in neither; exact McNemar `p=1`.
Lead rate was not a declared endpoint, and no win-rate claim is supported.

## Mechanism

The expansion-to-citizen-score path independently replicated:

- founder-production changes increased `+0.45` `[+0.33, +0.58]`;
- settlements and founded cities increased `+0.55` `[+0.43, +0.67]`;
- retained cities increased `+0.53` `[+0.42, +0.66]`;
- citizen score increased `+1.60` `[+1.09, +2.11]`; and
- technology and residual-score intervals included zero.

Treatment created 53 incremental retained cities across 51 pairs and reached
five total cities in 42 games. No baseline reached five cities.

Observed paired score deviation was 3.468. The 100-pair cohort exceeded the
predeclared 95-pair variance-planning requirement, achieved estimated 82.2%
power for its one-point design, and had an achieved detectable delta of
approximately 0.972.

## Correctness, safety, and replay

All 200 current streams and 290,741 events pass schema, ordering, proof,
provenance, and causal validation without errors or warnings. Exact replay
covered all 100 treatment traces and 7,878 pressure decisions. Every
selection and schedule hash reproduced with zero integrity failures and
unchanged sources. Paired initial states matched, engine rejection and model
safe-fallback rates were zero, and every full loop remained under 30 seconds.

One treatment startup attempt for seed `4644101` failed before gameplay
because the observer global state was not populated. Same-source resume reused
all 199 manifest-identical completed arms and replaced only that attempt. The
final cohort has 200 current completed arms and zero active infrastructure
failures; the original failure remains historical audit evidence.

The replay structural artifact hash is
`3e1f72b5cfbecf30c0c5eb017b97e62bf8c36e2a5a2be501157cf00a1d0ec314`;
its source-set hash is
`49b3fb4c185bcb9635900b0260f5fabe2250c0657b0265f619f380d103323b34`.
The aggregate byte SHA-256 is
`f7510f6cc632371229f6ab0a983e18b2144131d9abfd8bba7e74416e89e64d11`;
the replay byte SHA-256 is
`1408a3e08c9aa68933908e337188f00f500b0fb279d1073ce3f049a80d9794ca`.

## Claim boundary

The supported incremental claim is:

> On 100 fresh paired `civ2civ3` games against the configured experimental
> Freeciv AI, at turn 60, raising the grounded planner's expansion target from
> four to five cities while retaining a 15-turn settlement runway increased
> own score by 1.56 points on average, with a 95% paired-bootstrap interval of
> [0.88, 2.23] and exact paired p=1.998e-5.

This is separate from the earlier supported three-to-four-city `+2.66`
claim. The two estimates are not pooled or added into a direct
three-to-five-city claim. This result is not a win-rate claim, a
strictly-greater-than-two-point claim, or evidence for another ruleset,
opponent, horizon, planner configuration, or unpaired execution.

Machine-readable evidence is
[`pf-expansion-fifth-city-confirmatory-v1.json`](pf-expansion-fifth-city-confirmatory-v1.json).
