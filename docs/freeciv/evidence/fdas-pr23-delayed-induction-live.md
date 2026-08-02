# FDAS PR23 delayed induction outcome-label confirmation

Status: accepted engine-live mechanism evidence; delayed label lifecycle
`shadow-live`; delayed-label induction readout remains disabled; no score or
gameplay-improvement claim.

## Result

A fresh clean 160-turn FreeCiv engine run exercised the delayed induction
target introduced after the all-positive immediate-relief holdout result. The
dedicated activation profile opened one persistent label only after an
authoritative `goal-relief-observed` defense episode and resolved each label
from authoritative own state exactly eight turns later.

The independent audit accepted all nine gates:

- exact dedicated config, manifest capability, target, and eight-turn window;
- schema-valid causal event ledger with no warnings;
- hash-valid episode and label stores with no quarantine;
- one exact target label for every immediate-relief episode;
- no observation before the declared due turn;
- lifecycle event/store agreement;
- status counter/store agreement;
- zero truth mutation, policy authority, or induced-rule readout;
- clean source identity and completed fixed horizon.

The report structural hash is
`3997cf83ffaa5032f2de907bfd43037b5ff14f2619b1a48a12d200cdfe144bb5`.
The machine-readable report is
[`fdas-pr23-delayed-induction-live-engine.json`](fdas-pr23-delayed-induction-live-engine.json).

## Cohort

| Property | Result |
|---|---:|
| Source commit | `8808be55232ede49519a427951eca6d9671eb893` |
| Source dirty | no |
| Seed | `4543804-00` |
| Requested / reached horizon | 160 / 160 turns |
| Accepted / rejected engine actions | 367 / 0 |
| Immediate-relief episodes | 5 |
| Delayed labels opened / observed / pending | 5 / 5 / 0 |
| Positive / negative delayed labels | 5 / 0 |
| Induced proposals / promoted rules | 0 / 0 |
| Event records | 31,066 |
| Event-schema errors / warnings | 0 / 0 |

The five observed `(relief turn, due turn, observation turn, outcome)` rows
were:

```text
(1,  9,  9,  true)
(24, 32, 32, true)
(32, 40, 40, true)
(38, 46, 46, true)
(47, 55, 55, true)
```

The run proves that the delayed lifecycle is live, durable, restart-bound, and
decision-safe. It does **not** prove that the target discriminates useful
actions: all five outcomes were again positive. The delayed label is not yet
fed into live mining, candidate ranking, or rule readout.

## Retained evidence

The validated event ledger SHA-256 is
`7c6193a9b12241c11d98d501d1c7ab6900c5c920e90b53fad63e10bf5f0b16b7`.
The delayed-label store SHA-256 is
`e695fa24b7dd124a6fd8ccbd9dee06f3c6bb1b5f78d80695c6a950358e2433ec`.
Exact hashes for the manifest, status, episode store, label store, and event
ledger are recorded in the machine-readable report.

Two earlier launch directories are excluded from the cohort. `v1` failed
before gameplay because `FREECIV_RULESET_ROOT` was absent. `v2` reached the
first label and then failed closed because the FDAS emitter's narrower causal
event allowlist lacked the two already-published label event types. Commit
`8808be5` added that allowlist and its regression test; only the subsequent
clean `v3` run is accepted evidence.

## Reproduction

```bash
FREECIV_PROXY_WS=ws://127.0.0.1:8002/llmsocket/8002 \
FREECIV_API_TOKEN=test-token-fc3d-001 \
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data \
FREECIV_SERVER_CONTAINER=fciv-net \
OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_defense_delayed_induction_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_defense_delayed_induction_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_harness.py \
  --config profile/freeciv_harness_gdo5_160_turn.yaml \
  --out artifacts/freeciv/fdas-delayed-induction-live-160-v3 \
  --backend engine-live --workers 1 --base-port 6001 \
  --limit-seeds 1 --condition e_full_loop --main-only --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_delayed_induction_live.py \
  --game-dir artifacts/freeciv/fdas-delayed-induction-live-160-v3/games/main/e_full_loop/4543804-00 \
  --output docs/freeciv/evidence/fdas-pr23-delayed-induction-live-engine.json
```

## Next gate

The next scientific increment must create a predeclared engine population with
real outcome contrast without manufacturing negative labels. Suitable sources
are naturally consequential reinforcement episodes across independent seeds,
longer observation windows or stricter combat-capable coverage targets, and
threat/lifecycle strata where coverage can genuinely fail. Only after a frozen
train/holdout split contains independent positive and negative outcomes should
the delayed labels be enabled in offline mining and evaluated for residual
candidate discovery, calibration, and contradiction rate.
