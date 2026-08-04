# FDAS PR78 coordinated-replacement candidate-readout confirmation

Date: 2026-08-04

## Result

The known-opportunity engine confirmation passes every preregistered gate from
clean commit `9d0f5be342441bd53fc2bb994609176fdd27bda0`. Seed `109459`
completed the 160-turn horizon without resume or infrastructure failure. All
297 engine actions were accepted and the 54,022-event ledger is valid without
warnings. Engine gameplay took 131.56 seconds.

The separately gated replacement readout produced:

- 9 current readout evaluations;
- 33 coordinated-replacement candidate rows;
- 41 protected direct-move control rows;
- 33 grounded safe-chain pairs;
- zero pair rejections; and
- zero readout abstentions.

Thus every observed replacement candidate was connected to one exact unsafe
direct control and a current safe two-step chain. Every pair has a persistent
lifecycle reference, a reservable current binding and RequirementSet context,
authoritative source and target routes, and combined ETA/cost equal to the sum
of those routes. The component made no transition-value estimate and changed
no action selection, readout authority, policy authority, or truth.

The deterministic audit is
`fdas-pr78-coordinated-replacement-candidate-readout.json`, structural hash
`9cc6274f068637a459c000c3e6a5bbd00efeef5621c656d4cb29cb3a6432b4e1`.
A second invocation produced byte-identical output. Its embedded parent
lifecycle audit hash is
`f32519848a62e1298a3c70c255c137965d1f1c1ad27bd9be96eca527e0809eaa`.

## Interpretation

PR76's singleton-surface bottleneck is no longer a candidate-generation or
mechanical-grounding problem on this known seed: 33 safe coordinated
alternatives are now readable where direct movement was excluded to protect a
source garrison. This does not mean those chains are beneficial. Their value
must be learned against an outcome whose observation window begins only after
the second step reaches the target, not after the replacement first step.

The next gate is an unseen-seed recall cohort. Only after recall appears in at
least two independent games should the system define and calibrate a
chain-completion transition-value target. The existing 32-turn direct-action
calibration cannot be reused as if the chain were a one-step action.

## Claim boundary

This is known-seed, shadow-only candidate-recall evidence. It establishes no
transition-value accuracy, preference quality, action execution, causal goal
relief, score improvement, or win rate.
