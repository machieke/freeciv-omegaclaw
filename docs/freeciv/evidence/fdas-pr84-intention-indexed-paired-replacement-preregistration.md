# FDAS PR84 intention-indexed paired replacement preregistration

Date: 2026-08-04

## Scientific question

PR82 proves that one coordinated-replacement chain can execute and complete,
but its only strict durability label is negative. PR83 shows why that Boolean
is insufficient for cross-arm value: both cities survived while both assigned
actors were later killed defending. A control arm may never complete the chain,
so a completion-indexed endpoint cannot compare treatment with legacy policy.

PR84 asks a narrower question: after the same first grounded replacement
opportunity, does executing the bounded chain change 32-turn city retention,
garrison coverage, or assigned-actor attrition relative to leaving the exact
legacy controller in authority?

This is a claim-ineligible paired mechanism cohort. It is not sized for a score
or win-rate claim.

## Assignment and pairing

The independent analysis cluster is the engine seed. Each of 16 fixed fresh
seeds is run once under each arm:

- `control`: observe and durably assign the lexicographically first grounded
  PR78 chain, but retain the exact legacy action policy; and
- `treatment`: assign the same logical actor/source/target chain and apply the
  frozen PR82 exact multi-snapshot execution authority.

Arm is fixed in the manifest before gameplay. No treatment code may affect
either arm before the first grounded opportunity. The pair is usable only when
both arms identify the same assignment turn and logical tuple
`(replacement actor, reinforcement actor, source city, target city)`. A
mismatch is a mechanical failure, not missing outcome data.

The 16 fixed seeds are:

`109701, 109703, 109709, 109721, 109723, 109727, 109741, 109751, 109789,
109793, 109807, 109819, 109829, 109831, 109841, 109843`.

All were absent from checked profiles and evidence when this document was
written. No seed may be replaced, retried as evidence, or appended after
inspection. Launch order within each pair is deterministically alternated by
the low bit of `SHA256(experiment ID, seed)`; this controls systematic arm-order
effects without changing assignment.

The byte encoding is frozen as UTF-8
`fdas-replacement-intention-paired-pilot-v1:<base-10-seed>`. A zero low bit
launches control then treatment; a one low bit launches treatment then control.
Different seed pairs may run concurrently, but the two arms within one pair
must remain serial.

## Intention-indexed outcome

Both arms open one immutable outcome record at the shared assignment turn. Its
due turn is assignment turn plus 32. Assignment after turn 128 is explicitly
censored at the 160-turn horizon and cannot be counted as observed.

At the first authoritative snapshot at or after the due turn, record this
unweighted vector:

- source city owned and present;
- target city owned and present;
- own persistent-defender count at each city tile;
- whether each city has at least one persistent defender;
- replacement actor present and at the source;
- reinforcement actor present and at the target;
- each actor's transport state;
- exact disappearance cause and evidence quality for each absent actor;
- operation completed, failed, expired, or remained incomplete; and
- treatment step attempts, acceptances, rejections, and completion turn.

The original PR81 32-turn exact-actor durability label remains a separate
treatment-side endpoint when completion occurs. It is not substituted for the
intention-indexed vector.

## Estimands and analysis

Primary paired endpoint: treatment-minus-control difference in
`both_cities_owned_and_present` among mechanically matched opportunity pairs.

Secondary paired endpoints:

- total cities retained (0–2);
- total cities with a persistent defender (0–2);
- total assigned actors surviving (0–2);
- exact combat-attributed assigned-actor losses (0–2); and
- treatment chain completion.

Report every pair and every component. For binary endpoints, report discordant
pair counts, the paired risk difference, an exact two-sided sign/McNemar test,
and a 95% paired bootstrap interval over seed clusters. For bounded counts,
report the mean paired difference and the same seed-pair bootstrap interval.
No multiplicity-adjusted confirmatory claim is made; secondary endpoints are
descriptive.

## Missingness and attrition

- no opportunity in both arms: retain in the fixed denominator and report as
  `no-opportunity`, but exclude from local endpoint estimation;
- opportunity in only one arm or logical/turn mismatch: mechanical failure;
- both opportunities after turn 128: matched censored pair, retained but not
  observed;
- one outcome missing, one arm infrastructure-failed, or one arm eliminated
  before a scheduled observation: incomplete pair and mechanical failure;
- genuine absorbing terminal after an observed endpoint remains usable; and
- pending labels are never imputed as negative or positive.

## Mechanical acceptance

- all 32 fixed arms run from one clean source commit with no resume;
- all event ledgers validate with zero warnings;
- all engine actions have results and zero are rejected;
- control emits assignment and outcome evidence but zero replacement-execution
  authority or selection changes;
- treatment grants authority only to the one assigned exact chain and retains
  every PR82 final-gate and lifecycle invariant;
- at least four of 16 seed pairs have matched, observed opportunities;
- every observed pair has a complete consequence vector in both arms; and
- the cohort report is deterministic byte-for-byte.

If fewer than four pairs contribute, preserve the result as an under-yield
pilot. Do not add seeds. A later cohort must be separately preregistered.

## Progression rule

Mechanically complete data permits a separately preregistered larger discovery
cohort. It does not promote policy. A positive-value progression signal
requires all of:

- the primary paired city-retention point estimate is nonnegative;
- no treatment excess in engine rejection or unexplained actor removal;
- at least two independent pairs complete a treatment chain; and
- the full vector shows that any city-retention gain is not hidden behind an
  unbounded increase in assigned-actor attrition.

No confidence interval is required to exclude zero in this 16-pair pilot.

## Claim boundary

PR84 can establish comparable intention-indexed outcome mechanics and provide
a small paired descriptive signal. It cannot establish calibrated transition
value, general policy improvement, score impact, or win rate.
