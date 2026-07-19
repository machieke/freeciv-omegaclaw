# Paired impact-policy evaluation

## Purpose and estimands

The paired impact track measures whether bounded same-turn failover improves FreeCiv
outcomes. The game seed is the experimental unit; actions within a game are correlated
and never count as independent samples.

The fixed-horizon endpoints are deliberately explicit:

- `score_turn_n`: player score at the configured turn horizon, the primary endpoint;
- `opponent_score_turn_n`: opponent score at the same horizon;
- `score_margin_turn_n`: player minus opponent score;
- `score_lead_turn_n`: one only when player score exceeds opponent score at the horizon.

`score_lead_turn_n` is a fixed-horizon lead-rate endpoint. It is not described as an
engine-reported terminal FreeCiv victory; `terminal_win_metric` is explicitly null
until that engine contract exists. Ties are predeclared as non-wins. The legacy
`game_win` metric remains in the general M7 aggregate for compatibility but is not used
by the hardened paired claim path.

The treatment comparison holds condition, model, opponent, ruleset, horizon, machine
class, and server lifecycle fixed. Baseline sets
`max_no_effect_failovers_per_scope: 0`; treatment sets it to `4`. One worker runs both
arms consecutively and alternates which arm goes first across seed pairs.

## Cohorts and fresh seeds

`profile/freeciv_harness.yaml` predeclares four mutually disjoint cohorts. Literal
development seeds are retained for regression evidence. Fresh cohorts use
`sha256-counter-v1`; the committed namespace, counter rule, range, and count determine
every seed before any game is observed.

| Cohort | Purpose | Pairs | Claim eligible | Endpoints |
|---|---|---:|---|---|
| `development` | prior development/regression seeds | 100 | no | score, lead rate |
| `pilot` | variance and discordance estimation | 40 | no | score, lead rate |
| `confirmatory_score` | fixed score test | 100 | yes | score only |
| `confirmatory_joint` | hierarchical score then lead-rate test | 450 | yes | score, lead rate |

Configuration validation rejects overlapping cohorts. Pilot and confirmatory cohorts
require a clean Git checkout. The runner refreshes source identity immediately before
execution and again after the last arm; a dirty, unavailable, or changed identity
invalidates the run. Confirmatory cohorts also reject `--limit-pairs`.

If implementation hardening exposes any confirmatory seed before the final source is
frozen, that whole cohort is retired. The score-confirmatory `v3` namespace uses the
fresh range `1000000..1099999`. The superseded `v1` and `v2` namespaces are
development diagnostics and cannot be resumed into the final claim; `v2` exposed an
accepted-unit/no-authoritative-update edge case that required implementation changes.

## Statistical declaration

The score design uses two-sided alpha `0.05`, 80% target power, and a two-point minimum
detectable difference. Observed paired variance and achieved-power fields are
suppressed until at least 30 pairs complete. A 100-pair score design supports the
two-point target when paired SD is no greater than the predeclared planning bound
`7.13`.

Primary score and paired lead-rate intervals use 20,000 fixed-seed bootstrap samples
over seed-pair differences. The score endpoint also uses an exact two-sided paired
sign-flip randomization test. Under the sharp null, treatment and baseline labels are
exchangeable within each seed pair; dynamic programming evaluates the complete null
distribution. FreeCiv scores and declared score margins must be integers. The test
fails closed instead of becoming approximate if it exceeds its predeclared one-million
state bound.

Lead-rate testing additionally reports the four paired outcome cells and exact
two-sided McNemar p-value. The joint design predeclares a 10-percentage-point absolute
delta, discordance `0.50`, and 450 pairs; its exact McNemar design power exceeds 80%.

Claims use hierarchical gatekeeping:

1. score is tested first from all predeclared pairs;
2. the lead-rate test opens only if the score gate passes;
3. a score claim requires both its 95% interval lower bound above zero and its exact
   paired-randomization p-value at most `0.05`;
4. a lead-rate claim requires its paired interval lower bound above zero and exact
   McNemar p-value at most `0.05`;
5. the stronger “at least two score points” claim repeats both the interval and exact
   paired-randomization checks after centering at the two-point meaningful margin;
6. an “at least ten percentage points” lead-rate claim requires its interval lower
   bound above that meaningful margin.

No claim is produced unless the cohort is confirmatory, every predeclared pair is
complete, source freeze and absolute safety gates pass, and no active failure or order
violation remains. Pilot variance is planning evidence only and cannot be used as a
favorable early-stopping rule.

## Commands

Development orchestration smoke, permitted on a dirty worktree:

```bash
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/impact-development-smoke \
  --backend representative --cohort development --limit-pairs 5 --no-resume
```

After committing all implementation/configuration changes, run the fresh real-engine
pilot:

```bash
FREECIV_RULESET_ROOT="$FREECIV_LLM_ROOT/freeciv/freeciv/data" \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/impact-pilot-engine \
  --backend engine-live --cohort pilot
```

Run exactly one preselected confirmatory design. The score design executes 200 games;
the joint design executes 900 games:

```bash
FREECIV_RULESET_ROOT="$FREECIV_LLM_ROOT/freeciv/freeciv/data" \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/impact-confirmatory-score-engine \
  --backend engine-live --cohort confirmatory_score

FREECIV_RULESET_ROOT="$FREECIV_LLM_ROOT/freeciv/freeciv/data" \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/impact-confirmatory-joint-engine \
  --backend engine-live --cohort confirmatory_joint
```

Runs resume only manifest-identical completed arms. `--aggregate-only` rebuilds a
selected cohort report without executing games. Superseded attempts remain under
`attempt-history/`; active failures exclude both arms from paired estimates, and
historical failures remain visible.

## Outputs and interpretation

The track writes per-arm manifests/events/status plus `impact-run-summary.json`,
`impact-aggregate.json`, `impact-report.md`, and `impact-aggregate-events.jsonl`.
The aggregate includes endpoint definitions, cohort identity, source-freeze evidence,
score and McNemar power plans, paired intervals, exact score-randomization evidence,
safety gates, and a machine-readable `claim_evaluation` explaining every supported,
gated, ineligible, or not-ready claim.

Representative results validate orchestration and deterministic statistics only; they
are never gameplay evidence. A larger sample increases certainty but cannot turn a
null or negative treatment effect into a positive claim.

The hardened 100-pair development fixture at
`artifacts/freeciv/impact-paired-representative-hardening-100` completed all 200 arms,
balanced order 50/50, retained zero failures, and re-aggregated byte-identically to
SHA-256 `a93bb0e884d2ae014089d2e469ca6b60ed4fa759b8dcb503b8eada7dfd536d4b`.
Its deliberately favorable synthetic endpoints remain marked `ineligible` because
the cohort is development-only and its manifests record a dirty implementation tree.
