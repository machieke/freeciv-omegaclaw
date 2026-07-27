# PF-PLN fifth-city pilot v1

Status: complete; predeclared pilot advancement gate passed

The claim-ineligible `expansion_fifth_city_pilot_v1` cohort completed all 40
fresh pairs and 80 engine arms from clean commit `8e20718`. It independently
repeated the diagnostic's isolated fourth-to-fifth-city target change on
disjoint seeds. Both arms held adapter 1.17, a 15-turn settlement runway,
deadline recovery, packet-grounded site preference, pressure, learning, score
alignment, and disabled optional escort policies constant.

## Outcome

Mean turn-60 score increased from 118.975 to 120.650. The paired difference
was `+1.675`, with 95% paired-bootstrap interval `[+0.725, +2.575]` and exact
two-sided paired sign-flip `p=0.0015815`. Twenty-four pairs improved, nine
tied, and seven declined; total paired score increased by 67 points.

This passes the predeclared pilot advancement gates, but the cohort is not
claim eligible. The separate ten-pair diagnostic estimated `+1.1`
`[+0.1, +2.1]`; it is not pooled with this pilot.

The score mechanism replicated:

- settlements and founded cities increased `+0.575`
  `[+0.425, +0.725]`;
- retained cities increased `+0.525` `[+0.375, +0.675]`;
- citizen score increased `+1.85` `[+1.175, +2.55]`;
- technology score was unchanged; and
- residual score changed `-0.175` `[-0.675, +0.325]`.

Treatment created an incremental retained city in 21 pairs and reached five
cities in 17 games; no baseline reached five cities. Observed paired score
deviation was 3.033, and the achieved 40-pair design could detect
approximately 1.344 points under its variance-planning approximation.

Fixed-horizon lead rate changed `+0.075` `[-0.025, +0.175]`. Four pairs led
only under treatment, one only under baseline, eight in both arms, and 27 in
neither; exact McNemar `p=0.375`. This is favorable direction but not a
win-rate result.

## Integrity

All 80 logs and 116,819 events passed schema, ordering, proof, provenance, and
causal validation without errors or warnings. Exact replay covered all 40
treatment logs and 3,037 pressure decisions with zero integrity failures and
unchanged sources. Initial states matched; engine rejection and model fallback
rates were zero; every loop remained under 30 seconds. There were no
infrastructure failures.

The aggregate SHA-256 is
`164129b81c145ebe17a99aea51448eb9c56c1b9bd48cc0adfc79d7f9b349b7ea`;
the replay SHA-256 is
`1332e86e68adfc583aca455019735f78b88d43b484e81984d5dfe1e5f66cdf18`.
Machine-readable evidence is
[`pf-expansion-fifth-city-pilot-v1.json`](pf-expansion-fifth-city-pilot-v1.json).

## Confirmation

`expansion_fifth_city_confirmatory_v1` freezes the implementation and policy
on 100 fresh pairs derived from namespace
`pf-pln-expansion-fifth-city-confirmatory-v1`, range
`4500000..4699999`. It is score-only and powered for a one-point paired
effect at planning SD up to 3.5. It will not pool the diagnostic or pilot,
inspect outcomes early, or retune the policy.
