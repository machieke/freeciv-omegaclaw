# FDAS PR98 retained-capacity transition discovery preregistration

Date: 2026-08-04

## Question

PR97 measured the rare `effect-without-goal-relief` status in 3/64 fresh
games. Under the frozen exact-binomial design, 301 independent games give at
least a 90% chance of observing that status in 10 or more games at the 3/64
plug-in rate. PR98 asks whether a fixed 301-game discovery cohort supplies the
independent outcome diversity required to fit a shadow-only retained-capacity
transition-value model.

This is discovery and calibration evidence, not confirmation or policy
evidence. No PR97 row enters fitting.

## Frozen seeds and runtime

The exact 301 seeds are versioned in
`profile/freeciv_harness_fdas_pr98_retained_capacity_transition_discovery_160_turn.yaml`.
They are the first 301 prime values from 140009 upward that do not occur in any
versioned FDAS profile, evidence, preregistration, or instruction and do not
occur in any locally retained FreeCiv artifact manifest at registration time.

- seed count: `301`;
- first seed: `140009`;
- last seed: `143729`;
- ordered seed-list structural hash:
  `c8ff9f04b382d6cd53078142f505df7729cb0d27670b9260f61df1ed90a8bbcf`;
- collisions found after exclusion: `0`.

All games use the unchanged 160-turn full-loop engine profile and abstaining
PR95 query contract. Every seed remains in the denominator. No seed may be
replaced, retried, resumed, or appended based on query yield, outcome, score,
game result, or infrastructure behavior.

## Frozen dataset and adequacy gates

The accepted PR96 typed exporter supplies one terminal or right-censored row
per query and one ledger entry per game. The discovery dataset passes only if:

- all 301 jobs complete from one clean source commit with zero resume and zero
  infrastructure failure;
- every game passes the complete corrected PR95 audit chain;
- every query/episode join, identity, source, digest, partition, and authority
  gate passes;
- at least 30 terminal episodes exist;
- at least 20 independent games have a terminal episode;
- each terminal status has at least 10 episodes and occurs in at least 10
  independent games; and
- two complete exports are byte-identical.

Right-censored rows are retained but excluded from terminal-target fitting.
Zero-query games remain in rate denominators and cohort identity. Failure of a
diversity threshold is an accepted scientific result but keeps fitting
disabled.

## Frozen model target

A later PR99 fit may run only after every PR98 mechanics and adequacy gate
passes. Each terminal row maps to two nested binary outcomes:

| Terminal status | Exact product effect | Durable goal relief |
|---|---:|---:|
| `no-effect-observed` | 0 | 0 |
| `effect-without-goal-relief` | 1 | 0 |
| `goal-relief-observed` | 1 | 1 |

The controller-facing transition value is the predicted probability of
durable goal relief. Exact-product probability is retained as a separately
calibrated lifecycle diagnostic; it cannot be substituted for goal value.

## Frozen calibration hierarchy

Only the proposal-time PR95 categorical features may be used. Candidate
readout, score, opponent outcome, post-proposal state, terminal timing, and
future information are forbidden features.

Estimates use deterministic hierarchical backoff from the deepest eligible
level:

1. full PR95 feature signature;
2. action category, lifecycle state, production target, turn phase, and
   completion-horizon band;
3. action category, lifecycle state, and production target; and
4. action category plus lifecycle state.

A level is eligible only with at least 20 independent contributing games.
Point estimates are means of per-game outcome means so multiple queries from
one game do not create pseudo-replication. Uncertainty uses a deterministic
95% game-cluster bootstrap with 10,000 resamples and frozen seed `980301`.
The selected interval must have width no greater than `0.40`; otherwise the
query remains numerically abstained. Exact-product and goal-relief estimates
use the same hierarchy but separate samples and intervals.

No smoothing across production targets, feature selection, threshold search,
or retrospective level insertion is allowed. An unseen category backs off; an
unseen action/lifecycle root abstains.

## Frozen fitting and confirmation boundary

PR99 may serialize a deterministic model only if:

- every discovery adequacy gate passes;
- every fitted bin records exact query, episode, game, feature, target, level,
  and source-dataset provenance;
- bootstrap recomputation and model serialization are byte-identical;
- all training games and rows are listed once;
- PR97 and all earlier diagnostic rows are absent; and
- truth, learning write-through, conductance, readout, policy, and action
  authority remain false.

The discovery model stays offline/shadow-only. A disjoint fixed confirmation
cohort must independently meet the same diversity gates and preregister
calibration metrics before any candidate readout can consume a value.

## Frozen execution

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain)"

FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --out artifacts/freeciv/fdas-pr98-retained-capacity-transition-discovery-v1 \
  --config profile/freeciv_harness_fdas_pr98_retained_capacity_transition_discovery_160_turn.yaml \
  --backend engine-live --workers 4 --base-port 6001 \
  --condition e_full_loop --main-only --limit-seeds 301 --no-resume
```

The exact 301-game audit command and source commit are frozen in the PR98
cohort-audit implementation before launch.

```bash
SEEDS=$(python3 - <<'PY'
import yaml
with open(
    'profile/freeciv_harness_fdas_pr98_retained_capacity_transition_discovery_160_turn.yaml',
    encoding='utf-8',
) as stream:
    print(','.join(str(value) for value in yaml.safe_load(stream)['seeds']))
PY
)
PYTHONPATH=src:benchmarks python3 \
  scripts/freeciv/audit_fdas_retained_capacity_transition_discovery.py \
  artifacts/freeciv/fdas-pr98-retained-capacity-transition-discovery-v1 \
  --expected-seeds "$SEEDS" \
  --expected-source-commit "$SOURCE_COMMIT" \
  --audit-workers 4 \
  --output /tmp/fdas-pr98-retained-capacity-transition-discovery.json
```

## Claim boundary

A passing PR98 cohort establishes only discovery-data adequacy for the frozen
shadow model. It does not validate calibration, authorize numerical prediction
or candidate readout, establish causal action value, change gameplay, or
support a score or win-rate claim.
