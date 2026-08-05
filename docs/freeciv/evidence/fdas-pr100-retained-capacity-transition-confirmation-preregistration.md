# FDAS PR100 retained-capacity transition confirmation preregistration

Date: 2026-08-05

## Question

PR100 asks whether the exact frozen PR99 model is calibrated and at least
non-inferior to its root-only comparator on a disjoint, fixed engine cohort.
The model cannot be refitted, smoothed, thresholded, or otherwise changed from
PR99 after confirmation outcomes are observed.

This is transition-model confirmation. It is not candidate-readout, causal,
gameplay, score, or win-rate evidence, and passing it does not itself enable
any authority.

## Frozen model

The only permitted predictor is the canonical PR99 model:

- model result hash:
  `909e8170d9dc797f69b71337243633ddd5fd5e007a7627c44e150d0a05439a6f`;
- fit-report structural hash:
  `a6ad5fea69cbc62bb136350942334ac77cf7505006a66551de2308f7fd82065a`;
- serialized report SHA-256:
  `73a08cc72101fe82ba26bc0636a740a090767935bf4285d91e7195bd1203893d`.

The root-only comparators are also frozen from PR99: `0.37638888888888894`
for exact product effect and `0.2` for durable goal relief. Confirmation loads
the versioned model artifact and predicts proposal-time queries without
calling the fitter.

## Frozen seeds and engine cohort

The exact 301 seeds are versioned in
`profile/freeciv_harness_fdas_pr100_retained_capacity_transition_confirmation_160_turn.yaml`.
They are the first 301 primes from 150001 upward that did not occur in a
versioned file or any locally retained artifact manifest when registered.

- seed count: `301`;
- first seed: `150001`;
- last seed: `153499`;
- ordered seed-list structural hash:
  `5830695b4c6e1e8f3a2ba677bdb0b96745fea54ff8c2ead95e0fcf425ea67841`;
- collisions after exclusion: `0`.

The seeds are disjoint from PR98, PR97, and every earlier FDAS cohort. Every
seed remains in the denominator. No seed may be replaced, retried, resumed,
or appended based on queries, predictions, outcomes, calibration, score,
game result, or infrastructure behavior.

All games use the unchanged 160-turn full-loop engine profile and abstaining
PR95 query capture. The live controller does not load PR99 and is behaviorally
identical to PR98; model evaluation occurs offline after the fixed cohort.

## Frozen mechanics and diversity gates

Confirmation mechanics pass only if:

- all 301 jobs complete from one clean source commit with zero resume and zero
  infrastructure failure;
- every game passes the complete corrected PR95 audit chain;
- every query/episode identity, lineage, digest, source, partition, censoring,
  and authority gate passes;
- every proposal-time query receives exactly one prediction from the exact
  frozen PR99 model and no fitter is invoked; and
- two complete confirmation audits are byte-identical.

The PR98 diversity gates must independently pass: at least 30 terminal rows,
at least 20 terminal-bearing games, and at least 10 episodes plus 10
independent games for each of the three terminal statuses. Right-censored rows
remain explicit and are excluded from target metrics. Zero-query games remain
in all cohort-rate denominators.

Failure of mechanics rejects the cohort. Failure of diversity or calibration
is an accepted negative scientific result but keeps model confirmation and
all readout authority disabled.

## Frozen evaluation unit and bootstrap

Both targets use the PR99 binary mapping. For each terminal-bearing game and
target:

- Brier score is averaged across that game's terminal query rows;
- model-minus-root Brier difference is averaged across those same rows;
- predicted-minus-observed calibration difference is the game's mean
  prediction minus its mean binary outcome.

Overall metrics are unweighted means of those per-game means. Multiple queries
from one game therefore do not create pseudo-replication. The one model value
used for a row is the proposal-time prediction selected by the frozen PR99
hierarchy; later status and timing cannot enter prediction.

Brier and calibration metrics are conditional on terminal rows for which the
model supplies a numerical prediction. An abstained row is never imputed as
zero, `0.5`, or the root comparator. The separate 90% numerical-coverage gate
limits selective abstention, and all terminal, censored, and abstained rows
remain explicitly counted in the report.

Every uncertainty interval uses a separate deterministic 10,000-resample
game-cluster bootstrap with seed `1000301`. Games are sorted by numeric seed
and game ID before sampling. Each bootstrap sample draws `n` games with
replacement, estimates the requested mean, sorts the 10,000 values, and uses
zero-based order statistics `250` and `9750` as its 95% endpoints.

## Frozen confirmation thresholds

All of the following must pass for both exact product effect and durable goal
relief unless explicitly narrowed:

1. at least 90% of terminal query rows receive a numerical prediction;
2. overall per-game Brier score is no greater than `0.25`;
3. the 95% bootstrap interval for mean predicted-minus-observed calibration
   difference lies entirely within `[-0.10, +0.10]`;
4. the upper 95% bootstrap endpoint for model-minus-root Brier difference is
   no greater than `+0.02`;
5. for durable goal relief, the point model-minus-root Brier difference is
   strictly below `0.0`;
6. at least four target/selected-bin groups contain at least 20 independent
   confirmation games;
7. for every such group, the absolute point calibration difference is no
   greater than `0.15`; and
8. at least 80% of such groups have their unweighted confirmation per-game
   outcome mean inside the frozen PR99 interval for that selected bin.

The product target is diagnostic but must still pass its calibration and
non-inferiority gates. The durable-relief target is primary and additionally
must show point Brier improvement over the root comparator. No threshold may
be relaxed and no new metric may be promoted to acceptance after seeing the
confirmation cohort.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr100-retained-capacity-transition-confirmation-v1 \
  --config profile/freeciv_harness_fdas_pr100_retained_capacity_transition_confirmation_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 301 --no-resume
```

The exact confirmation evaluator and audit command will be committed before
launch. The engine cohort must start only from that clean evaluator commit.

```bash
SEEDS=$(python3 - <<'PY'
import yaml
with open(
    'profile/freeciv_harness_fdas_pr100_retained_capacity_transition_confirmation_160_turn.yaml',
    encoding='utf-8',
) as stream:
    print(','.join(str(value) for value in yaml.safe_load(stream)['seeds']))
PY
)
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/audit_fdas_retained_capacity_transition_confirmation.py \
  artifacts/freeciv/fdas-pr100-retained-capacity-transition-confirmation-v1 \
  --expected-seeds "$SEEDS" \
  --expected-source-commit "$SOURCE_COMMIT" \
  --model-report \
    docs/freeciv/evidence/fdas-pr99-retained-capacity-transition-model.json \
  --audit-workers 4 \
  --output /tmp/fdas-pr100-retained-capacity-transition-confirmation.json
```

## Claim boundary

A passing PR100 result would confirm out-of-sample calibration and bounded
Brier performance for this exact model on the retained-capacity query domain.
It would not prove causal action value, safe candidate displacement, gameplay
impact, score improvement, or win rate. Candidate readout would require a
later, separately preregistered decision-safe shadow comparison before any
authority could be considered.

## Pre-launch feasibility correction

Before implementing the evaluator or launching any confirmation game, a dry
run on the already published PR98 discovery rows showed that the originally
written per-bin interval-equivalence gate was structurally underpowered. With
the frozen minimum of 20 independent games, a binary bin can have exactly zero
point calibration error while its 95% resampling interval still extends beyond
`[-0.15, +0.15]`. Two exactly self-reproducing 26- and 27-game discovery bins
demonstrated that issue.

Criterion 7 therefore uses absolute point calibration difference no greater
than `0.15`. The stronger overall interval-equivalence criterion 3 remains
unchanged, as do the four-bin minimum, 80% frozen-interval containment,
coverage, Brier, and non-inferiority gates. This correction uses no PR100 data;
no PR100 engine game has started.
