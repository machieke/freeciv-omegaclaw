# FDAS PR84 intention-indexed paired replacement outcome

Date: 2026-08-04

## Result

The frozen PR84 cohort is mechanically rejected and supplies no usable value
claim. All 32 fixed arms ran once, without resume, from clean source commit
`18abdf294e891189654f94d88ac9dac20ad4737d`. All 16 control arms completed;
10 of 16 treatment arms completed and six ended in preserved controller
infrastructure failures. No failed arm was retried or replaced.

The deterministic audit classifies the 16 seed pairs as:

- 4 `no-opportunity`;
- 10 `opportunity-mismatch`;
- 1 `outcome-mismatch`; and
- 1 `matched-observed`.

There are no matched-censored or incomplete-directory pairs. All launch orders
match the preregistered SHA-256 low-bit order, all 32 arms share the expected
clean source, and all fixed arms are present.

## Primary mechanical finding

PR84's first-opportunity selection was not arm-invariant. It sorted by the
lifecycle operation ID, whose structural identity contains arm-specific goal
material. In every one of the 11 pairs where both arms exposed a grounded
candidate surface, the logical candidate-surface hashes match. Nevertheless,
10 pairs selected different logical tuples or otherwise failed matching; only
seed `109841` selected the same tuple and reached an observed endpoint in both
arms. Seed `109829` had a control-only opportunity.

For example, seed `109703` exposed the same eight logical candidates at turn
33. Control selected `(123, 117, 110, 121)` while treatment selected
`(123, 117, 110, 112)`. The lexicographic logical minimum in both arms was
`(123, 106, 101, 112)`. This directly identifies arm-local operation ordering,
not candidate recall, as the principal pairing defect.

## Preserved treatment failures

Six treatment arms failed in three repeated integration classes:

- two exceeded a turn-ETA-derived operation attempt limit even though the
  native route required more accepted tile actions;
- three authorized an exact grounded step when the legacy planner had no
  baseline decision, but the integration layer required one to construct the
  replacement `ImpactDecision`; and
- one could not rematerialize the next byte-identical legal operation step
  through legacy candidate filtering/category matching.

The treatment arms recorded 57 submitted replacement attempts and all 57 were
accepted by the engine. Thus the failures are controller integration failures,
not engine rejections. Three treatment chains completed, but their pairs are
not valid value observations except for seed `109841`.

## Descriptive endpoint boundary

The sole matched-observed pair, seed `109841`, retained both cities in both
arms and lost one assigned actor to exact combat in each arm. Treatment minus
control was:

- `0` for both-city retention;
- `0` for city-retention count;
- `-1` for defended-city count;
- `0` for assigned-actor survival; and
- `0` for exact combat-attributed actor losses.

One pair is below the preregistered minimum of four matched observed pairs, so
these numbers are diagnostic only. The zero city-retention estimate and its
degenerate one-pair bootstrap interval are not evidence of equivalence, harm,
or benefit.

## Conclusion and correction

PR84 proves that intention-indexed outcome collection, exact disappearance
attribution, fixed arm ordering, and full-denominator failure preservation work
end to end. It does not establish treatment value. Mechanical acceptance,
minimum yield, and the progression rule all fail.

PR85 was preregistered before any corrected engine seed. It orders by logical
tuple before operation ID, derives attempt capacity from native route length,
permits exact materialization without a legacy baseline, and protects an active
exact operation step from legacy candidate suppression/category drift. PR84 is
not pooled with PR85 and remains permanently failed evidence.

The canonical report is
`fdas-pr84-intention-indexed-paired-replacement.json`, with structural hash
`91eefc8471ba9b882acce0b87dc124f0e2b6c1f83387d8753d672f0515561780`.

