# FDAS PR31 promoted-rule shadow preregistration

Status: frozen before fresh engine collection; no fresh outcome has been
inspected; no induced-rule authority, gameplay, score, or win-rate claim.

## Frozen implementation

The shadow-readout implementation is frozen at clean commit
`5fddb90`. It consumes the exact PR29 approvals and PR30 consolidation,
reproduces the four-rule basis, and cannot alter truth, policy, action ranking,
or action selection.

Readout is outcome-blind. For each future episode it:

1. identifies approved retained rules whose context and antecedents match;
2. discards matching rules that are strict antecedent subsets of another
   matching retained rule;
3. reports a 95% Wilson interval for every maximal estimate;
4. accepts a unique maximal estimate;
5. accepts multiple same-direction estimates only when their intervals overlap,
   choosing the estimate with the smallest absolute departure from baseline;
6. abstains when maximal estimates disagree in direction or have disjoint
   uncertainty intervals; and
7. records `truth_mutated=false`, `policy_authority=false`,
   `readout_authority=false`, and `action_selection_changed=false`.

The evaluator reports candidate and baseline Brier score, log loss, exact-
prediction calibration error, a deterministic 10,000-sample paired bootstrap
interval for Brier improvement, coverage, conflict rate, and context strata.

## Retrospective design check

PR29 was used only to debug the mechanics before this freeze. The final policy
read all 14 PR29 confirmation episodes with zero conflicts and had a conditional
Brier improvement of `+0.00460`; its paired 95% interval was
`[-0.02233, +0.02829]`. Those values are disclosed because they influenced the
final conflict policy. They are not validation evidence and cannot enter the
fresh claim.

## Fresh cohort

The next six untouched pinned seeds are fixed as one complete cohort:

```text
104911, 104917, 104933, 104947, 104953, 104959
```

Every seed will use:

- the 160-turn `e_full_loop` engine-live condition;
- the `civ2civ3` ruleset and experimental built-in opponent;
- `qwen3-coder-next:latest` at temperature zero;
- `defense-episode-features/3.0`;
- the 32-turn `durable-attributed-actor-city-defense/32-turn/1.0` label;
- the existing bounded defense controller, with induced-rule readout disabled;
  and
- clean-source, horizon-complete, warning-free event and delayed-label audits.

All six games will be collected before evaluation. Collection will not stop,
extend, replace seeds, or change thresholds based on observed outcomes.

## Predeclared gates

The component shadow-readout result is accepted only if:

- all six engine sources are clean, horizon-complete, and audit-valid;
- at least 20 delayed outcomes are encoded;
- at least 12 episodes receive a shadow prediction;
- conflict abstentions are at most 20% of encoded episodes;
- conditional candidate Brier score is no worse than the matched baseline;
- every evaluation remains non-authorizing and action-preserving; and
- the complete artifact chain and report hashes validate.

The paired bootstrap interval is a claim classifier, not a collection stopping
rule. A lower bound above zero would support statistically resolved predictive
improvement for this narrow executed-operation target. A crossing interval
supports only a directional estimate. Neither result establishes intervention
value or FreeCiv score improvement; those require a later randomized,
action-selection experiment.

## Reproduction

```bash
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN=test-token-fc3d-001 \
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_SERVER_CONTAINER=fciv-net \
OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_actor_persistence_causal_induction_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_actor_persistence_causal_induction_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --out artifacts/freeciv/fdas-promoted-rule-shadow-confirmation-live-160-v1 \
  --backend engine-live --workers 1 --base-port 6001 \
  --seed-offset 16 --limit-seeds 6 \
  --condition e_full_loop --main-only --no-resume
```

The frozen evaluator will then receive all six episode stores and all six
outcome-label stores with:

```text
--minimum-encoded 20
--minimum-readouts 12
--maximum-ambiguity-rate 0.20
--minimum-brier-improvement 0.0
--minimum-brier-lower-bound -1.0
--require-engine-source --require-horizon --require-clean-source
```
