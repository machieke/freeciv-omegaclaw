# FDAS PR37 action-family and route-attribution smoke

## Claim boundary

This is a repeated-seed engineering differential. It verifies candidate
sampling, ambiguity handling, lifecycle attribution, and event integrity. The
seed and intermediate implementations were inspected during development, so
none of these artifacts is eligible for discovery, calibration, ranking,
gameplay, score, or win-rate claims.

## Corrections

PR36 showed that sampling was coupled to legacy rationale categories. PR37
changes the observational trigger to the exact selected action family:
`unit_move` or `unit_fortify`. The legacy planner still selects every action,
and an episode still requires one byte-identical legal FDAS binding.

The first broadened smoke exposed a one-action/multiple-goal ambiguity. A
single legal move can be the first step toward more than one deficient city.
Those bindings are now omitted from attribution, with a metric and structural
hash, unless exactly one operation owns the action key.

The next differential showed that a multi-turn route was closed before goal
relief. Basic garrison operations now carry the authoritative server route ETA
as their expiry turn. Episode attribution remains open through that inclusive
turn and closes at the next boundary. Unchanged pending effects are not
republished.

Finally, candidate calibration exports now carry game, selected actor, action
type, and operation type lineage. Yield audits count conservative
`(game, actor, action stratum)` clusters and require observed lineages, so a
single sequential route cannot masquerade as independent support.

## Final engineering result

Clean commit `1f5528a` completed seed `104801` through turn 160 with 351
accepted engine actions, zero rejections, no infrastructure failure, and
32,628 valid events.

The action-family surface produced:

- 86 opportunity sets and 300 exact unambiguous choices;
- 71 multi-candidate and 24 mixed move/fortify sets;
- 74 explicitly censored no-selection opportunities;
- 12 selected actions: seven moves and five fortifications;
- eight observed delayed outcomes: three move rows and five fortification
  rows;
- six positive and two negative outcomes;
- three selected move actor lineages, but only one observed move lineage; and
- five selected and observed fortification lineages.

Relative to the immediately preceding same-seed route-window differential,
inclusive expiry recovered the first two route steps: observed move rows rose
from one to three. All three belong to one actor/route lineage and therefore
count as one independent cluster. Unchanged-effect suppression reduced the
event ledger from 35,281 to 32,628 records.

The run passes every mechanical, candidate-recall, mixed-stratum, selection,
contrast, and selected-lineage gate. It intentionally fails the minimum total
outcome and observed move-lineage gates. A fresh multi-seed yield cohort is
required before discovery.

## Evidence

- Machine report:
  `docs/freeciv/evidence/fdas-pr37-action-family-route-smoke.json`
- Report hash:
  `fcc6f739130a3fc6e7f59b17524fe730a597e0ceb44a3b11c54e5b72acacb2d2`
- Machine-report SHA-256:
  `b9f70c29257601f809cb2f866f8e1192a28901ac57615c2e0b1d5240743ef39f`
- Candidate-choice audit hash:
  `fca1206d6056e0064647e30c9629151c136019d8ee00d78eef5aba5b4e10d0a1`
- Choice-store SHA-256:
  `07923bf2c3edd436253c5170ed9a1ba1b881f47592318c66874aeddb73672a37`
- Choice-store digest:
  `904dcf983c88cc262b4ae1549cdaaffbd540f39bb3c3a6de4d78929df7e2f30e`
- Event-ledger SHA-256:
  `d51e4f88fc90866d60442e6c28e38ebb18eb008c5ab17d23b1c97a1e5e0c5c9d`
