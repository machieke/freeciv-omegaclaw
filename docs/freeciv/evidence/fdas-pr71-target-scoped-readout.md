# FDAS PR71 target-scoped scalar readout cohort

## Primary result

PR71 passes every frozen mechanics and comparison-yield gate. All eight fixed
games from clean commit `586e248` completed with zero harness failures,
infrastructure failures, rejected actions, or resumes. The parent safety and
target-chain audit passes without authority leakage.

The primary report is `fdas-pr71-target-scoped-readout.json`, hash
`5a3d370063282ed74b4c271484eeefe8929bdef9b4988945e1d566a639919e83`.

## Target-scope mechanics

The PR67 filter partitioned 708 observational candidates, excluding all 456
source-garrison-unsafe candidates and admitting 252. Across 210 nonempty safe
surfaces, the target filter admitted 211 candidates and excluded 41 candidates
whose operation type or exact target differed from scalar top-1. It preserved
the full upstream candidate records and emitted one target scope with a
non-baseline candidate; the other 209 scopes were singletons.

The additions-only union emitted 210 readouts and 211 members. It made exactly
one calibrated addition beyond scalar top-1, with 37 candidate-specific and 24
broad-backoff estimates overall. Every union is causally bound to a target
filter, every target filter to its safety filter, and all runtime counters match
the immutable events.

## Grounded comparison

The one addition became a fully grounded same-target alternative at seed
`109229`, turn 39, for city 118 and support atom
`atom-2afa48e0b0e1256f32eb1ecb37bdde2a`:

- scalar control: Riflemen actor 124, ETA 2, total movement cost 12,
  estimate `0.4275`, interval `[0.1920, 0.6631]`;
- protected alternative: Alpine Troops actor 108, ETA 1, total movement cost
  6, estimate `0.4389`, interval `[0.1952, 0.6827]`.

The actors and resources are distinct, both candidates ground to the same city
and support atom, and the alternative reaches the target faster at lower route
cost. Their calibrated intervals overlap almost completely, so the frozen
readout correctly abstains with `calibrated-interval-overlap`. There are zero
preferences and zero action changes.

## Interpretation and next gate

PR71 resolves the semantic recall defect: a protected calibrated alternative
can now reach the correct scalar decision scope. Yield remains sparse—one
multi-candidate scope in 210—and the confirmed transition model does not
discriminate the observed pair. Do not narrow intervals or drop separation
post hoc.

The next bounded diagnostic should compute and expose grounded noninferiority
checks independently of interval separation. The current evaluation stops at
overlap, so it does not reveal that route checks favor the alternative while
the exact-unit-type equality check may reject an otherwise stronger unit. Any
future relaxation must replace type equality with ruleset-grounded defensive
capability, not a name-based allowlist, and still requires fresh evidence.

## Claim boundary

PR71 establishes target-scoped, safety-filtered grounded-comparison mechanics
only. It does not establish calibrated discrimination, preference correctness,
counterfactual value, gameplay benefit, score improvement, or win rate. It
grants no policy, readout, truth, flow, capacity, or action-selection authority.
