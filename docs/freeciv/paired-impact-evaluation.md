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

If `PACKET_PLAYER_INFO.is_alive` becomes false before the horizon, the exact
authoritative terminal score is an absorbing observation carried forward to the
horizon. An eliminated player cannot accrue further score. The run records
`score_observation_turn`, `horizon_reached=false`,
`terminal_player_elimination=true`, and
`score_observation_semantics=terminal_absorbing_score_carried_to_horizon`.
Asset emptiness is never used to infer this terminal state.

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

`profile/freeciv_harness.yaml` predeclares mutually disjoint cohorts. Literal
development seeds are retained for regression evidence. Fresh cohorts use
`sha256-counter-v1`; the committed namespace, counter rule, range, and count determine
every seed before any game is observed.

| Cohort | Purpose | Pairs | Claim eligible | Endpoints |
|---|---|---:|---|---|
| `development` | prior development/regression seeds | 100 | no | score, lead rate |
| `diagnostic_unitless_city_v1` | unitless-city state regression | 1 | no | score, lead rate |
| `diagnostic_terminal_elimination_v1` | exposed terminal-state regression | 2 | no | score, lead rate |
| `pilot` | variance and discordance estimation | 40 | no | score, lead rate |
| `pilot_horizon_60` | superseded turn-60 planning pilot | 40 | no | score, lead rate |
| `pilot_horizon_60_v2` | hardened turn-60 planning pilot | 40 | no | score, lead rate |
| `pilot_horizon_60_v3` | pre-confirmation turn-60 pilot | 40 | no | score, lead rate |
| `pilot_horizon_60_v4` | current-policy turn-60 pilot | 40 | no | score, lead rate |
| `confirmatory_score` | retired exposed V4 score cohort | 100 | no | score only |
| `confirmatory_score_horizon_60_v1` | completed prior-policy turn-60 score test | 200 | yes | score only |
| `confirmatory_score_horizon_60_v2` | retired incomplete current-policy test | 450 | no | score only |
| `confirmatory_score_horizon_60_v3` | retired operational-latency test | 450 | no | score only |
| `confirmatory_score_horizon_60_v4` | retired terminal-state-contract test | 450 | no | score only |
| `confirmatory_joint` | hierarchical score then lead-rate test | 450 | yes | score, lead rate |

Configuration validation rejects overlapping active cohorts. Diagnostic, pilot, and
confirmatory cohorts require a clean Git checkout. The runner refreshes source identity immediately before
execution and again after the last arm; a dirty, unavailable, or changed identity
invalidates the run. Confirmatory cohorts also reject `--limit-pairs`.

If implementation hardening exposes any confirmatory seed before the final source is
frozen, that whole cohort is retired. The score-confirmatory `v4` namespace uses the
fresh range `1100000..1199999`. The superseded `v1`, `v2`, and `v3` namespaces are
development diagnostics and cannot be resumed into the final claim; `v2` exposed an
accepted-unit/no-authoritative-update edge case, while `v3` exposed cold-model
unloading that produced bounded-timeout fallbacks. The v4 engine runner performs an
operational native Ollama chat request before every arm, validates its complete JSON
response, and uses a 90-second cold-load allowance plus a 30-minute keep-alive. This exercises
the same endpoint and decoder as a timed proposal instead of stopping after a one-token
generation. A claim-eligible arm fails closed if any turn still needs a model fallback; it is
retried only as a fresh attempt and never silently counted as a completed pair.

## Statistical declaration

The score design uses two-sided alpha `0.05` and 80% target power. Observed paired
variance and achieved-power fields are suppressed until at least 30 pairs complete.
The original 100-pair design used a two-point minimum detectable difference and a
paired-SD bound of `7.13`. It is retained only as historical configuration because
its seeds were already exposed.

The hardened turn-60 pilot estimated a `+0.20` score delta and paired SD `0.8533`.
The completed `confirmatory_score_horizon_60_v1` cohort therefore predeclared a
`0.20`-point minimum detectable difference, raises the maximum planning SD to `1.0`,
and fixes 200 pairs. The paired-normal calculation requires 197 pairs at that bound;
200 was frozen before any confirmatory arm was observed. Its observed paired SD was
`1.4056`, for which 388 pairs would have been required at the same target; its achieved
power was 52.1%, although its positive-improvement inference still passed.

The current-policy `confirmatory_score_horizon_60_v2` design was frozen independently
of all exposed V4 pilot seeds. It uses 450 deterministic seeds in the disjoint
`1900000..1999999` range, a conservative maximum planning SD of `1.5`, and the same
`0.20`-point detectable difference. The paired-normal calculation requires 442 pairs,
leaving eight pairs of design margin. The 0.20-point resolution is also the excess
needed to distinguish the pilot's apparent `+2.20` effect from the separately declared
two-point meaningful-effect threshold; the actual cohort is analyzed regardless of
whether that pilot estimate reproduces. There is no interim outcome inspection,
adaptive stopping, seed replacement, or pooling with earlier cohorts.

V2 was retired after 899 of 900 arms completed. Treatment seed `1905459`
reproducibly reached authoritative turn 25 with two owned cities and zero owned units,
but the engine harness rejected every unitless snapshot before its separate elimination
check. Three fresh attempts failed at the same boundary. Because correcting this state
contract changes the implementation identity, the 899 completed arms remain immutable
diagnostic evidence and cannot be completed or pooled into a claim. The one-pair
`diagnostic_unitless_city_v1` cohort validates the correction at the default turn-30
horizon before a new disjoint confirmation design is frozen.

That diagnostic completed both arms from clean commit `eb20498`. The treatment
authoritative snapshots at turns 25 and 30 each contained two cities and zero units;
all safety and paired-fidelity gates passed, and the complete 1,457-event release audit
passed. V3 therefore freezes the unchanged 450-pair score design in the fresh
`2000000..2099999` range under namespace
`pln-freeciv-impact-confirmatory-score-horizon60-v3-unitless-state`. Its 0.20-point
detectable difference, 1.5 planning-SD bound, source-freeze rules, and claim gates are
identical to V2. V2 outcomes are not used for V3 sizing, seed selection, or inference.

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
  --out artifacts/freeciv/impact-pilot-horizon60-v2-engine \
  --backend engine-live --cohort pilot_horizon_60_v2
```

Historical V1 score confirmation and the joint design execute 400 and 900 games,
respectively:

```bash
FREECIV_RULESET_ROOT="$FREECIV_LLM_ROOT/freeciv/freeciv/data" \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/impact-confirmatory-score-engine \
  --backend engine-live --cohort confirmatory_score_horizon_60_v1

FREECIV_RULESET_ROOT="$FREECIV_LLM_ROOT/freeciv/freeciv/data" \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/impact-confirmatory-joint-engine \
  --backend engine-live --cohort confirmatory_joint
```

The current configuration deliberately removes retired V2 from active cohort selection.
Its exact configuration remains reproducible from commit `d078114`, but it must not be
resumed into a claim. Validate the unitless-city correction with the active diagnostic:

```bash
FREECIV_RULESET_ROOT="$FREECIV_LLM_ROOT/freeciv/freeciv/data" \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/impact-unitless-city-1905459 \
  --backend engine-live --cohort diagnostic_unitless_city_v1
```

Validate the packet-backed terminal correction against both exposed failing seeds.
This runs four arms so both seed pairs remain complete; three are the former failures
and treatment seed `2146151` is their paired control:

```bash
FREECIV_RULESET_ROOT="$FREECIV_LLM_ROOT/freeciv/freeciv/data" \
PYTHONPATH=src:benchmarks python3 scripts/freeciv/run_impact_evaluation.py \
  --out artifacts/freeciv/impact-terminal-elimination-v1-engine \
  --backend engine-live --cohort diagnostic_terminal_elimination_v1 \
  --workers 2 --server-ports 6001,6002
```

The original `confirmatory_score_horizon_60_v4` remains reproducible from commit
`b59205c57a481bda657d7a71af9657fd014f87fb`, but its 897 old-code completions
cannot be pooled with corrected terminal arms. It is retired with three active
infrastructure failures rather than relabeled or source-mixed.

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
