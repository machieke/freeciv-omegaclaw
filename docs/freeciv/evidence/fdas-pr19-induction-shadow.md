# FDAS PR19 episode-induction shadow evidence

## Scope

This slice connects durable engine-live defense episodes to the bounded
contextual pattern miner. It is a learning observation path only: accepted
episode encodings may create immutable candidates in a durable quarantine
ledger, but the profile disables induced-rule readout and the runtime rejects
any promoted rule loaded into this shadow path.

It does not claim that a useful rule was learned, that held-out validation is
live, that an induced rule affected an action, or that score or gameplay
improved.

## Implemented boundary

`FdasEpisodeInductionShadow` reads the compact `DecisionEpisodeStore`, applies
the fail-closed episode adapter, and mines only causally attributable terminal
outcomes. Context is restricted to the exact operation type; candidate
features are the actor's pre-action tile and target tile already carried by
the episode. Pending, contradicted, expired, and confounded rows cannot become
positive training evidence. Shared execution provenance makes mining abstain
rather than inflating independent support.

The miner is bounded to support four, two antecedents, residual 0.05, and 32
candidates. `InductionLedger.propose()` can only introduce a candidate with
status `quarantined`. This live slice never calls replay validation. The
ledger is persisted even when empty, so a zero-proposal/zero-promotion result
is independently hash-verifiable rather than inferred from a missing file.

Every evaluation emits a causal latency sample with accepted and abstained
encoding counts, mining reason, result hash, ledger hash,
`truth_mutated=false`, and `policy_authority=false`. A newly proposed rule
would emit `induced_rule_quarantined`; promoted, demoted, and validation events
are forbidden by the audit.

## Fresh engine confirmation

The clean 160-turn `e_full_loop` run used seed `4543804`, source commit
`60f97e944a2bbb911a17a7c1d90576a9e95314ae`, and implementation SHA-256
`36d2f15c99bc68e05479f88c7d71d07904cd6138427c971577d0036eaeddec11`.
The live profile retained the independently gated bounded defense authority;
induction itself had no readout or authority.

| Measure | Result |
| --- | ---: |
| Horizon | 160 / 160 turns |
| Engine actions / accepted results / rejects | 353 / 353 / 0 |
| Attributable terminal episodes | 5 |
| Causal induction evaluations | 5 |
| Episode encoding abstentions | 0 |
| Maximum induction latency | 0.502 ms |
| Quarantined proposals | 0 |
| Promoted rules | 0 |
| Event records | 29,409 |
| Event-schema errors / warnings | 0 / 0 |

All five outcomes were `goal-relief-observed`. Consequently, the population
contained no contrasting result by tile or operation context, and no pattern
cleared the residual gate. Zero proposals is therefore the correct bounded
result for this cohort, not evidence that induction quality is good or bad.
Demonstrating useful discovery requires a predeclared training cohort with
independent, attributable positive and negative outcomes.

The deterministic audit accepted all nine gates. Its structural hash is
`4f9405dd5a7c36e935e9e1ad36acc6bf7a165e7cb534fe49a4f4b30c4ab22bf8`.
The machine-readable report is
[`fdas-pr19-induction-shadow-engine.json`](fdas-pr19-induction-shadow-engine.json).

## Reproduction

```bash
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_induction_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_induction_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --out artifacts/freeciv/fdas-induction-shadow-live-160-v2 \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_induction_live.py \
  --game-dir artifacts/freeciv/fdas-induction-shadow-live-160-v2/games/main/e_full_loop/4543804-00 \
  --output docs/freeciv/evidence/fdas-pr19-induction-shadow-engine.json
```

The environment also needs the existing FreeCiv proxy URL/WebSocket, server
container, ruleset root, Ollama OpenAI-compatible base URL, and API token.

## Claim boundary and next gate

This closes engine-live attributable episode encoding and durable
quarantine-only induction for the bounded defense slice. Held-out replay and
promotion remain component-only, and induced-rule readout stays disabled. The
next scientific gate is a frozen, independent train/holdout design containing
both goal-relief and no-relief outcomes. It must first show that the miner
produces stable residual-gated candidates, then validate calibration and
contradiction behavior on disjoint provenance before any separate,
default-off readout experiment can be considered.
