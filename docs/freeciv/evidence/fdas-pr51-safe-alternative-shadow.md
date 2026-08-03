# PR51 safe alternative-outcome shadow

## Decision

PR51 establishes that the live defense surface can occasionally form two
byte-identical-in-shape, independently resource-safe reinforcement actions and
assign one with a stable recorded propensity. It does **not** execute the
assignment and therefore provides no causal candidate-value, gameplay, score,
or win-rate claim.

The persistence-only design was rejected before intervention: it produced no
eligible assignments in the engineering smoke. A bounded nearest-score design
produced one eligible pair in one 160-turn game. This is enough to exercise the
mechanics, but its observed yield is too low to proceed directly to a large
cohort.

## Fail-closed contract

An eligible pair requires all of the following in the same current revision:

1. the active legacy winner is a legal FDAS city-garrison move;
2. both operations have a unique action binding and an admissible typed score;
3. both use the same operation slice, unit class, movement cost, and target
   action while reserving distinct actor resources;
4. priority regret is at most `0.01` and risk-penalty delta is zero;
5. both routes independently pass native-server-path, deficit-atom,
   source-garrison, resource/packet, and exact commit preflight;
6. the assignment is a deterministic hash draw with explicit arm propensity;
7. truth, score/readout, flow, and action authority remain false.

The optional target-reference equality gate remains explicit. The accepted
engineering pair happened to share `city:115` even though the exploratory
profile did not require it.

## Engine evidence

The final engineering smoke used seed `105491`, a 160-turn horizon, and source
commit `98ad580`. It completed cleanly with 406 accepted engine actions, zero
rejections, and 47,091 events.

| Measure | Result |
|---|---:|
| Alternative evaluations | 166 |
| Eligible assignments | 1 |
| Ineligible evaluations | 165 |
| Control assignments | 1 |
| Treatment assignments | 0 |
| Assignment executions | 0 |
| Selection changes | 0 |
| Persistence memberships added | 38 |

The ineligibility decomposition was:

| Reason | Count |
|---|---:|
| Active winner outside configured defense slice | 156 |
| No bounded nearest-score alternative | 7 |
| No unique FDAS route for the active winner | 2 |

At turn 17, actor `112` was the control and actor `117` the treatment. Both
were Musketeers moves with movement cost `6`, the same target action and city,
zero typed priority, zero risk penalty, distinct `unit-action` resources, the
same deficit atom, and independent pressure, packet, and commit proof hashes.
The stable draw was `0.6244487`, selecting control at propensity `0.5`.

## Yield and next gate

One eligible assignment per observed 160-turn game implies roughly 30 games
for 30 assignments if the rate persists. At the measured runtime of about 170
seconds per game, that is approximately 85 minutes before audit and fitting.
This estimate is highly uncertain because it is based on one game.

The next gate is therefore a small, claim-ineligible execution pilot, not a
score experiment. It must prove exact revalidation, assigned-action execution,
accepted/rejected linkage, durable episode linkage, and propensity-preserving
delayed labels. Any rejection, stale binding, authority escape, source-garrison
violation, or outcome-linkage ambiguity stops the pilot. Only its measured
assignment yield may determine whether a larger randomized collection cohort
is practical.

