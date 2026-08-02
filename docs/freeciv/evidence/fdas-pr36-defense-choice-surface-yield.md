# FDAS PR36 defense choice surface yield result

## Result

The preregistered cohort passed all nine mechanical audit gates and failed the
frozen scientific progression gate. Do not fit a transition model on this
cohort.

All seeds (`104773`, `104779`, and `104789`) reached turn 160 from identical
clean commit `bf19272952c01b50e766607d80de6fbd0261f045`. Across 52,666 events
there were zero validation errors, warnings, rejected actions, or
infrastructure failures. All three choice stores are current, independent,
non-quarantined, outcome-free, selected-only, and explicitly non-authorizing.

## Frozen-gate outcome

The cohort produced 13 choice sets, 21 exact legal candidates, 12 in-scope
selections, 11 observed delayed outcomes, nine positives, and two negatives.
It passed the actor/context, multi-candidate, and outcome-contrast gates.

It failed three frozen gates:

- observed selected outcomes: 11, required at least 12;
- mixed move/fortify sets: two, required at least three;
- selected action strata: 12 fortifications and zero garrison moves, required
  at least two of each.

The one-outcome shortfall is not the primary blocker. Zero selected move
support makes any cross-action fitted comparison unidentified even if the
total outcome threshold were lowered, which is forbidden.

## Root-cause analysis

Candidate materialization did not truncate the move stratum: the stores
contain nine exact legal garrison-move rows and 12 fortification rows. The
moves appeared only as censored alternatives. Every selected row was a
fortification.

The live sampling boundary was coupled to the legacy candidate category. It
evaluated the surface for `city_defense` and `city_garrison_move` winners, not
for the exact selected action family. The three fresh games selected 203 unit
moves, but none carried the narrow `city_garrison_move` rationale, so those
decisions were never checked for exact overlap with a legal FDAS garrison
operation.

PR35's apparently strong move yield was also less independent than its raw set
count suggested. All ten selected garrison moves came from one seed, one actor,
and one sequential relocation lifecycle over turns 47–63. The fresh result
therefore shows that legacy category occurrence, not FDAS candidate
availability, controlled move-label support.

This is a sampling-semantics failure. Adding same-cohort seeds, treating
censored moves as negative, pooling the sequential PR35 moves as independent,
or fitting a cross-action model would all create an invalid claim.

## Bounded correction

The next implementation increment should make surface evaluation depend on
the exact selected action family (`unit_move` or `unit_fortify`) rather than
the legacy rationale category. It must still:

- require a byte-identical match before opening an episode;
- record no-selection opportunities explicitly;
- leave every nonselected candidate censored;
- avoid invoking defense authority for out-of-authority move categories;
- preserve action selection unchanged; and
- group later calibration and validation by game/actor/lifecycle so sequential
  relocations are not treated as independent evidence.

Only a separately preregistered clean cohort may test whether this correction
recovers independently useful selected-move support.

## Evidence

- Machine report:
  `docs/freeciv/evidence/fdas-pr36-defense-choice-surface-yield.json`
- Report hash:
  `ae236ec0b55e0e475cdfba62e74c3275c89d35668ae3c089a7d0a9bfe9eb5ba7`
- Machine-report SHA-256:
  `147191e3e482ac28bf442240d20e70bb1a5fdd7f12f517f169c2e44255a56e9a`
- Combined choice-store digest:
  `da136cb3beb6e874b55f31354f2767bb8f1cfff924e42db9eb0aef766b8548de`
- Candidate-choice audit hash:
  `7c92518c54b9f18ff975aac9000fcb2356b32cd8ab3428f584c554c7bda6d275`
- Seed event-ledger SHA-256 values:
  `134045e214b3d1e640d0b07f74f088111723e0bc94f4dbe460e352999893b710`,
  `4274072a6346da6c50f2ac35d9fdb262294ef990d67f8ace0e2dd5a0415b0998`,
  and `b7292c887372a195eef8ca918a8eae07a152ef4399b2b21b0f61562d39cbdca5`.

Claim scope remains mechanism and yield only. There is no model-fit,
calibration, ranking, decision-safety, gameplay, score, or win-rate claim.
