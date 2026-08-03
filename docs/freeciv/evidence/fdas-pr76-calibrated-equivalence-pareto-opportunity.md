# FDAS PR76 calibrated-equivalence Pareto opportunity cohort

Date: 2026-08-03
Runtime source: `d2f3799`
Audit report: `fdas-pr76-calibrated-equivalence-pareto-opportunity.json`
Report hash: `092d81b2e7b44feece4fd38d6f6456316183305e3f00be04bde57d1f3503f914`

## Result

The preregistered 16-seed unseen cohort is mechanically accepted. All 16
fixed games completed without retry or resume, the inherited endpoint, ledger,
counter, filter, target, union, rejection, and authority audits passed, and all
5,101 engine actions were accepted. Every one of the 567 scalar readouts used
only calibrated-equivalence Pareto identity `1.2`. Median per-game engine
runtime was 430 seconds and the maximum was 785 seconds.

The cohort produced 17 fully grounded same-target alternatives in three of 16
games. Six alternatives had at least one strict grounded improvement, all in
seed `109459`. Four of those six also had exact estimate, interval, lineage,
and prediction-reason equivalence and full grounded noninferiority, so they
emitted non-authorizing shadow preferences. No independently interval-separated
preference occurred.

Equivalence-Pareto preferences therefore appeared in one of 16 independent
game clusters: point rate `0.0625`, descriptive 95% Wilson interval
`[0.0111, 0.2833]`. The frozen classification is
`equivalence-pareto-preference-observed`. The four repeated decisions within
seed `109459` are not treated as four independent samples.

## Opportunity funnel

The inherited safety filter processed 2,797 candidates, retained 794, and
excluded 2,003; every exclusion was a protected source-garrison case. Target
scoping then retained 588 candidates and rejected 206 candidates serving a
different operation type or city target. Across 567 target-scoped decisions,
550 surfaces were singletons. The protected union contained 584 members and
only 17 additions, exactly matching the 17 grounded alternatives observed by
the readout.

This locates the dominant loss before comparative calibration:

- `96.99%` of target-scoped decisions (`550/567`) had no second safe candidate;
- grounded alternatives appeared in `3/16` games, point rate `0.1875` with
  descriptive interval `[0.0659, 0.4301]`;
- strict improvement appeared in `1/16` games, the same cluster that produced
  every preference; and
- once a strict improvement existed, four of six rows passed the exact
  calibrated-equivalence Pareto rule.

Increasing the calibrated-per-action union bound alone has little ceiling in
this cohort: target scoping exposed only 21 candidates beyond the mandatory
567 controls, and the existing union already retained 17 of them. The larger
opportunity loss is the absence of multiple safe, same-target reinforcement
routes. In particular, moving a sole source-city garrison is correctly rejected
unless an exact replacement lifecycle protects that city.

## Interpretation and next gate

Readout `1.2` transfers to unseen engine states and remains decision-safe, but
its current game-level opportunity rate is too sparse for an economical causal
value cohort. At the observed point rate, a large randomized game cohort would
mostly measure no-assignment games and the repeated rows in one game would not
repair the independent-cluster deficit.

The next bounded implementation should preserve the readout, calibration,
target, and source-garrison safety gates and improve candidate generation. The
highest-value route is to project an exact coordinated-replacement candidate
when a protected source garrison can be covered by a current legal replacement
step, then compare the resulting same-target reinforcement route in shadow.
This must remain a distinct multi-step lifecycle with exact requirements,
resource claims, revision checks, and no action authority. A smaller
calibrated-union-width sensitivity may be retained as a diagnostic, but it
cannot address the 550 singleton surfaces.

Only after at least two independent unseen game clusters expose a readout
preference should a separately preregistered randomized 32-turn selected-actor
outcome pilot be considered.

## Claim boundary

This cohort establishes unseen preference-yield and safety mechanics only. It
does not establish counterfactual ranking quality, treatment effect, gameplay
impact, score improvement, or win rate and grants no action authority.
