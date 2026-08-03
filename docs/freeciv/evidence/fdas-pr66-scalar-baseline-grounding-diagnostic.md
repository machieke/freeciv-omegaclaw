# FDAS PR66 scalar-baseline grounding diagnostic

## Result

PR66 passes from clean commit `b2e518c`. Fresh seed `109021` reached observed
turn 161 with no infrastructure failure, resume, or rejected action. The parent
PR65 mechanics audit is accepted, candidate-specific predictions occurred,
all generic control-grounding reasons were eliminated, and exact fail-closed
reasons were recorded.

Report `fdas-pr66-scalar-baseline-grounding-diagnostic.json` passes with hash
`ec958eb2dd8b993a909cdf5a07315375a0a07d2acf8079ace6a6acc285723c8d`.
Engine latency was 103.12 seconds.

## Root cause

The exact distribution is:

- 56 `control-bounded-validator-candidate-has-noncontractual-blockers`;
- 8 `scalar-baseline-is-not-reinforcement-move`;
- 1 `no-protected-alternative`; and
- 1 `no-separated-grounded-noninferior-alternative`.

Every one of the 56 rejected scalar controls carried the same blockers:
`protected-source-garrison` and `uncompiled-action-effect`. The bounded
reinforcement validator already permits `uncompiled-action-effect` because the
shadow action effect is deliberately uncompiled. It correctly rejects
`protected-source-garrison`: the exact defender-removal grounding proved that
moving the actor would create a defense deficit in its source city.

The route and actor transition features were therefore not contradictory.
They answered whether the move mechanics were completely observed. The later
safety validator answered a different necessary question—whether the source
city could safely release that actor. PR59 did not encode safety eligibility
as calibration input, and the protected union allowed such safety-blocked
candidates to become its scalar baseline or calibrated addition.

## Corrective direction

`protected-source-garrison` must not be added to the validator allowlist. The
candidate remains valuable as an observable explanation of why reinforcement
is unavailable, but it is not decision-safe. The next correction should form a
separate safety-filtered union surface before calibrated recall:

- retain the complete choice surface for censored observational records;
- run the existing exact fortify/reinforcement validators without granting
  authority;
- expose every excluded operation and exact reason;
- compute scalar top-1 and calibrated recall only over candidates that pass the
  matching bounded safety contract; and
- abstain if no safety-eligible candidate remains.

This prevents an unsafe operation from becoming either control or proposed
alternative while preserving the original scalar scores and all source-city
protection.

## Claim boundary

PR66 identifies a safety-filtering defect and proves exact diagnostic
mechanics. It does not establish candidate opportunity, preference, ranking,
counterfactual value, gameplay, score, or win rate, and it grants no authority.
