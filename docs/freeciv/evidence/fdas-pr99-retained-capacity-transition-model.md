# PR99 retained-capacity transition discovery model

Date: 2026-08-05

## Result

The frozen PR99 hierarchical shadow-model fit passes every construction,
source, provenance, roundtrip, recomputation, target, and authority gate. Two
complete fits from the canonical PR98 report are byte-identical.

- Model result hash:
  `909e8170d9dc797f69b71337243633ddd5fd5e007a7627c44e150d0a05439a6f`
- Fit-report structural hash:
  `a6ad5fea69cbc62bb136350942334ac77cf7505006a66551de2308f7fd82065a`
- Serialized fit-report SHA-256:
  `73a08cc72101fe82ba26bc0636a740a090767935bf4285d91e7195bd1203893d`

The model accounts for all 301 PR98 games and all 163 PR98 query rows exactly
once. It fits the 162 terminal rows and retains the one right-censored row as
an explicit non-training exclusion. PR97 and earlier rows are absent. Truth
mutation, learning write-through, model calibration, candidate readout,
policy, and action authority all remain false.

## Frozen hierarchy and coverage

The model materializes 156 target bins across the four preregistered hierarchy
levels. Twelve bins meet the minimum of 20 independent games; all twelve also
meet the maximum bootstrap interval width of `0.40`.

Exact 14-field signatures remain sparse: none has 20 independent games. The
model therefore uses only preregistered backoff levels for the discovery
queries:

| Selected level | Proposal-time queries |
|---|---:|
| Category + lifecycle + product + phase + horizon | 124 |
| Category + lifecycle + product | 17 |
| Category + lifecycle root | 22 |

All 163 proposal-time queries receive both product-effect and goal-relief
estimates. This is 100% **in-sample numerical coverage**, including a
proposal-time prediction for the row whose later outcome is censored. It is
not calibration, validation, or evidence of predictive accuracy.

## Discovery estimates

Every estimate is the unweighted mean of per-game means. Intervals are the
frozen 10,000-resample game-cluster bootstrap intervals.

| Context | Independent games | Exact product effect (95% interval) | Durable goal relief (95% interval) |
|---|---:|---:|---:|
| Category/lifecycle root | 120 | 37.6% (29.6% to 45.7%) | 20.0% (13.6% to 26.7%) |
| Riflemen, all phases | 82 | 43.3% (33.1% to 53.7%) | 22.4% (14.0% to 31.5%) |
| Alpine Troops, all phases | 34 | 24.0% (10.8% to 38.2%) | 14.2% (4.9% to 25.0%) |
| Riflemen, turns 0–39, horizon 33–64 | 57 | 46.8% (34.2% to 59.6%) | 24.3% (14.0% to 35.4%) |
| Riflemen, turns 40–79, horizon 33–64 | 27 | 35.2% (18.5% to 53.7%) | 13.0% (1.9% to 25.9%) |
| Alpine Troops, turns 0–39, horizon 33–64 | 26 | 26.9% (11.5% to 46.2%) | 17.3% (5.8% to 30.8%) |

The product target is never replaced by the smaller durable-relief target;
both remain separately estimated and target nesting is checked in every bin.
The model selects the deepest sample-eligible level before inspecting width.
No result obtains a more favorable interval by backing off a second time.

## Reproducibility and hardening

The typed artifact independently reconstructs every bin from the 162 typed
terminal rows, recomputes per-game means and all bootstrap intervals, and then
verifies its model hash. It rejects changed PR98 report bytes or structural
hashes, changed source lineage, duplicate games or rows, target violations,
forbidden hierarchy or bootstrap settings, interval tampering, and authority
leakage. Typed predictions erase estimate and interval values when abstained.

Both complete command-line fits serialized canonical JSON and matched by
literal byte comparison and SHA-256. The versioned JSON is one of those exact
outputs and contains the full source ledger, training and exclusion rows,
bins, per-game target means, predictions, checks, and false authority flags.

## Claim boundary and next gate

PR99 proves deterministic, provenance-complete model construction and
in-sample numerical coverage. It does not show calibration, out-of-sample
accuracy, causal transition value, better candidate selection, gameplay
impact, score improvement, or win rate. The model remains shadow-only and
cannot affect candidate readout.

The next step is a disjoint, fixed, preregistered confirmation cohort. It must
independently pass the PR98 mechanics and diversity gates and evaluate this
exact frozen model without refitting. Confirmation metrics and acceptance
thresholds must be frozen before that engine cohort starts.
