# PF-PLN fifth-city diagnostic v1

Status: complete; predeclared development advancement gate passed

The source-fresh, claim-ineligible
`expansion_fifth_city_diagnostic_v1` cohort completed all ten paired seeds and
20 engine arms from clean commit `8076650`. Both arms used planner adapter
1.17, a 15-turn post-settlement runway, deadline recovery, packet-grounded
site preference, pressure, conductance learning, and score alignment. All
optional escort policies were disabled. The only arm difference was
`expansion_city_target`: four under baseline and five under treatment.

## Result

Mean turn-60 score increased from 118.8 to 119.9. The paired difference was
`+1.1`, with paired-bootstrap interval `[+0.1, +2.1]`. Five pairs improved,
two tied, and three declined. The exact paired sign-flip p-value was
`0.109375`; ten selected development pairs are neither powered nor eligible
for a score claim.

The grounded mechanism activated:

- founder-production changes increased `+0.9` `[+0.6, +1.2]`;
- settlements and retained cities increased `+0.5` `[+0.2, +0.8]`;
- citizen score increased `+1.7` `[+0.6, +2.8]`;
- technology score was unchanged; and
- residual score changed `-0.6` `[-1.3, 0]`.

Four treatments reached the five-city target, and a fifth treatment gained
one more city than its baseline. The ten treatments therefore delivered five
incremental retained cities, exceeding the predeclared advancement threshold
of two. Mean score direction was positive, so the small diagnostic advances
to a separately predeclared fresh pilot.

Score-lead rate was unchanged: four pairs led in both arms and six in neither.
Score margin changed `+0.2` `[-1.1, +1.6]`; this diagnostic does not support
a win-rate or margin claim.

## Integrity

All 20 event logs and 28,556 events passed schema, ordering, provenance,
proof, and causal validation with zero errors or warnings. Exact replay
covered all ten treatment logs and 711 pressure decisions with zero integrity
failures and unchanged sources. Initial states matched; engine rejection and
model fallback rates were zero; every full loop remained under 30 seconds.
There were no infrastructure failures.

The aggregate SHA-256 is
`b4c7d726aa0bdf7948260f1050219770def4252c8d53de8b3bc40091788ae3cc`;
the replay SHA-256 is
`cd95aaa5f2d4c7b71d8b6af0854318bc42ebca891c789b37c37760bd1ecfe827`.
Machine-readable evidence is
[`pf-expansion-fifth-city-diagnostic-v1.json`](pf-expansion-fifth-city-diagnostic-v1.json).

## Next gate

`expansion_fifth_city_pilot_v1` freezes the same isolated fourth-to-fifth-city
comparison on 40 disjoint pairs from namespace
`pf-pln-expansion-fifth-city-pilot-v1`, range `4400000..4499999`. The pilot
must report all outcomes and cannot pool this diagnostic. Advancement to a
claim-eligible confirmation requires positive founding and citizen-score
mechanisms, a score interval above zero, exact paired `p <= 0.05`, and all
source, safety, schema, and replay gates.
