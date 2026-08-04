# FDAS PR83 replacement-chain consequence diagnostic

Date: 2026-08-04

## Result

The retrospective PR83 diagnostic passes all five frozen consistency gates on
the immutable PR82 run. It reproduces the accepted parent report hash, retains
the original negative durability label, and decomposes that label into two
retained cities, zero surviving assigned actors, and two exact
combat-attributed defender losses.

The actor histories are:

- reinforcement actor `108` (`Warriors`) disappeared on turn 53 at `(4, 13)`;
  `PACKET_UNIT_COMBAT_INFO` reported defender HP zero before the removal; and
- replacement actor `122` (`Musketeers`) disappeared on turn 74 at `(9, 12)`
  with the same exact defender-loss evidence.

Both source city `103` and target city `121` were still owned and present at
the turn-74 observation. The diagnostic does not convert that city retention
into a positive label: the registered exact-actor placement and transport
conjuncts still failed, so PR82 remains negative.

The deterministic report is
`fdas-pr83-replacement-chain-consequence-diagnostic.json`, structural hash
`75708a58bb7569af0545f1de6aae47e8737dd47c85e24666984cdb0836951155`.
A second invocation produced byte-identical JSON with SHA-256
`fb60c983a883c25db0d5dc4bff18d12b4a6c6c52b8f0e5cb2ea44a71208cdeae`.

## Interpretation

The negative PR82 result is not caused by food upkeep, disbanding, upgrade,
transport, unexplained removal, or loss of either city. Both assigned units
were consumed in later combat while defending. The replacement remained at
the source through fortification on turn 36, but ordinary policy moved it away
on turns 58 and 59, attacked with it on turns 64 and 72, and it was then killed
as a defender on turn 74.

This matters for endpoint design. Exact-actor survival and exact placement are
real resource/durability costs, but they are not interchangeable with city
survival. Adding an unconditional 32-turn actor lock solely to make the binary
target pass would optimize the measurement and could suppress legitimate
redeployment. Future transition-value work must keep city retention, garrison
coverage, assigned-actor attrition, placement persistence, and combat cause as
separate registered outcomes.

## Next boundary

A comparable control cannot use completion-indexed measurement because the
legacy arm may never complete the candidate chain. The next fresh paired-seed
design must therefore index primary local outcomes from the first grounded
assignment opportunity in both arms. Treatment may execute the frozen bounded
chain; control must continue the byte-identical legacy policy. The design must
also retain chain completion and PR81 durability as treatment-side mechanism
and cost endpoints rather than substituting them for the cross-arm outcome.

## Claim boundary

PR83 explains the components of one already observed known-seed result. It
does not establish that the treatment saved either city, caused either combat
loss, improved defense, or changed score or win rate.
