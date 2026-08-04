# FDAS PR77 coordinated-replacement live-wiring confirmation

Date: 2026-08-04

## Result

The corrected `v2` engine run passes every preregistered acceptance gate from
clean commit `f97b682aa27d138608491c787a794e78b839dc81`. Seed `109459`
completed the 160-turn horizon without resume, infrastructure failure, or
rejected engine action. The event ledger contains 54,007 schema-valid events
without warnings, and the engine accepted all 297 actions.

The live path exercised real opportunity rather than only empty activation:

- 33 coordinated-replacement candidate observations;
- 15 persistent, hash-valid operation records;
- 195 revision-current lifecycle updates;
- 34 `reservable` and 30 `reconciled` updates;
- 116 fail-closed `blocked` updates; and
- 15 expected shadow expirations.

There were zero step advances and zero completions because this slice is
non-authorizing: the baseline controller did not execute the replacement
operations. Every lifecycle event retained false policy authority, readout
authority, action-selection change, and truth mutation. The final store is
unquarantined and all operations are terminal, so no duplicate active logical
lifecycle remains. Engine gameplay took 131.77 seconds.

The deterministic audit report is
`fdas-pr77-coordinated-replacement-live-wiring.json`, structural hash
`3138ad0216e39ab1b3d293643925c8094d343a976e1572b2158ba3de2c5e2e9f`.
A second audit invocation produced byte-identical output.

## Preserved failure

The `v1` artifact remains a failed integration attempt. It reached turn 33,
then the first real candidate exposed a mismatch between the adapter's raw IR
payload hash and the candidate factory's canonical FDAS ruleset identity. The
adapter rejected it before any replacement action could be selected. The `v2`
run uses the canonical identity through both paths and proves the correction
on that same opportunity boundary.

## Interpretation and next gate

This closes live persistence, reconciliation, projection, requirement, and
event mechanics. It also demonstrates that exact replacement opportunities
are not intrinsically too rare on the known rich-defense game.

It does not yet improve candidate preference yield. The existing scalar
readout components contain no coordinated-replacement rows: the choice surface
is still limited to direct move and fortify operation types, while a
replacement is a two-step operation whose first action serves a source city
and whose operation target is the deficit city. The next bounded change must
give this operation its own protected readout representation and compare its
combined native route cost and arrival time against the protected direct move,
without pretending the first step alone relieves the target deficit.

## Claim boundary

This is known-seed, shadow-only integration evidence. It establishes no
independent opportunity rate, action value, gameplay effect, score gain, or
win-rate improvement.
