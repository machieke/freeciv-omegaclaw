# FDAS PR74 ruleset-defensive opportunity cohort

Date: 2026-08-03
Runtime source: `5678efc`
Audit report: `fdas-pr74-ruleset-defensive-opportunity.json`
Report hash: `27730078b56f3ab121332d52f3d0ad0ecd792b1ee1eb0886c8d7ea003587b093`

## Result

The preregistered 16-seed unseen cohort is mechanically accepted. All 16
games completed without retry or resume, all event ledgers and runtime counters
passed the inherited safety audit, all 4,686 engine actions were accepted, and
every one of the 350 scalar readouts used only ruleset-defensive identity
`1.1`. The median per-game engine runtime was 413 seconds and the maximum was
739 seconds.

The protected pipeline processed 2,972 safety-filter inputs, retained 765,
excluded 2,206 protected source-garrison candidates, and target-scoped 440
members across 350 readouts. It generated 53 additions-only recalls and 50
fully grounded same-target alternatives. Grounded alternatives appeared in
four of 16 games, a game-level rate of `0.25` with descriptive 95% Wilson
interval `[0.102, 0.495]`.

Two alternatives compared different unit types, in two of 16 games. Both
passed all ruleset defensive capability checks; the descriptive game-level
rate was `0.125`, interval `[0.035, 0.360]`. Thirty of the 50 alternatives were
noninferior on every grounded route, current-unit, and ruleset-capability check.

No alternative had a calibrated interval separated from its control. The
game-level separation rate was `0/16`, with descriptive 95% Wilson upper bound
`0.194`. Consequently all 350 readouts abstained and emitted zero shadow
preferences. The frozen classification is `no-interval-separation-yield`.

## Interval diagnosis

The failure is not marginal. Across all 50 comparisons:

- median alternative and control interval width was `0.4287`;
- the narrowest alternative-minus-control separation margin was still
  `-0.4142`;
- estimate deltas ranged only from `-0.0201` to `+0.0201`;
- 44 comparisons had no positive estimate delta; and
- the typical candidate had 17 effective lineages, yet remained on a broad
  action/lifecycle backoff.

Among the 30 grounded-noninferior alternatives, 28 had exactly the same
estimate, interval, and effective-lineage count as their controls. Twelve were
strictly better on at least one grounded dimension. Ten of those combined
strict mechanical improvement with an exactly identical calibrated readout:
nine recurring faster/lower-cost Riflemen reinforcements in seed `109433`, and
one better home-city relation between Alpine Troops in seed `109343`.

This shows that merely collecting more target-scoped candidates will not open
the current readout. The independent-marginal rule
`alternative.lower > control.upper` requires a gap over 0.41 while the largest
observed point-estimate advantage was only 0.02. The model also collapses many
mechanically distinct candidates onto the same backoff bin, so interval
narrowing alone would still leave most point estimates tied.

## Interpretation and next gate

PR74 moves the bottleneck from recall and defensive semantics to comparative
uncertainty. The next bounded comparator should keep scalar PF-v2 and the
ruleset readout frozen, then evaluate a versioned, shadow-only rule for exact
calibrated equivalence plus strict grounded Pareto dominance. This is supported
by ten already observed opportunities and does not require pretending that
overlapping marginal intervals establish statistical superiority.

A later paired-difference model should estimate the realized relief contrast
directly and preserve covariance between candidates. That model requires new
randomized or otherwise identifiable outcomes; the existing marginal intervals
cannot safely be transformed post hoc into a causal superiority interval.

## Claim boundary

This cohort establishes comparable-candidate and interval-yield mechanics only.
It does not establish counterfactual ranking quality, treatment effect,
gameplay impact, score improvement, or win rate and grants no action authority.
