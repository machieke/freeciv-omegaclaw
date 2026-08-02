# FDAS PR24 delayed-label held-out discovery gate

Status: mechanism/source gates accepted; required proposal gate rejected; no
promotion, readout, score, or gameplay-improvement claim.

## Frozen split and result

The first engine-backed held-out evaluation of the delayed target used the
predeclared split:

- training: seeds `4543804` and `104743`;
- holdout: seed `104759`;
- target: `durable-own-unit-city-coverage/8-turn/1.0`;
- strict requirements: clean engine sources, completed 160-turn horizons,
  nonempty accepted train/holdout populations, and at least one proposal.

All three engine games completed from clean commit
`23c05a489b02e5bbc0c681844a9ecc168e33aaf7` with no harness failures. The
runner accepted every source, partition, label, lifecycle, hash, horizon, and
authority gate. It rejected only `proposal_requirement_met`.

| Partition | Episodes encoded | Positive | Negative |
|---|---:|---:|---:|
| Training | 10 | 10 | 0 |
| Holdout | 7 | 7 | 0 |
| Total | 17 | 17 | 0 |

With no observed contrast, no contextual residual could exist. The miner
therefore correctly returned `no-pattern-cleared-residual-gate`, zero
proposals, zero validations, and zero promotions. The report structural hash is
`9f322dfb54a30b3468fbb780fe965dd57c8e802e775c8f0f465e7afe304e6950`.
The machine-readable rejected-gate report is
[`fdas-pr24-delayed-induction-holdout-engine.json`](fdas-pr24-delayed-induction-holdout-engine.json).

## Interpretation

This is a target-design failure, not a flow, persistence, serialization, or
mining failure. A fortification action is deliberately persistent, and “some
own non-transported unit remains in the city after eight turns” is too weak to
separate consequential outcomes in these games. Collecting more identical
eight-turn samples would increase confidence in that ceiling without creating
the missing counterfactual variation.

A post-hoc diagnostic over the retained authoritative snapshots tested a more
action-specific question: whether the attributed actor itself remained on the
target city tile in a fortified activity. This diagnostic is exploratory and
must not be treated as confirmation evidence:

| Window after relief | Available rows | Positive | Negative |
|---|---:|---:|---:|
| 8 turns | 17 | 17 | 0 |
| 16 turns | 17 | 14 | 3 |
| 24 turns | 17 | 13 | 4 |
| 32 turns | 17 | 12 | 5 |
| 48 turns | 17 | 8 | 9 |

The 32-turn actor-persistence target is the next bounded choice: it provides a
meaningful operation-lifecycle horizon and enough exploratory contrast without
making a half-game survival claim. It must be implemented as a new versioned
target and evaluated on fresh independent seeds; these 17 rows were used for
target selection and are ineligible for confirmation.

## Reproduction

```bash
ROOT=artifacts/freeciv/fdas-delayed-induction-population-live-160-v1/games/main/e_full_loop
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_fdas_induction_holdout.py \
  --training-store "$ROOT/4543804-00/fdas-decision-episodes.json" \
  --training-store "$ROOT/104743-00/fdas-decision-episodes.json" \
  --holdout-store "$ROOT/104759-00/fdas-decision-episodes.json" \
  --training-outcome-label-store "$ROOT/4543804-00/fdas-induction-outcome-labels.json" \
  --training-outcome-label-store "$ROOT/104743-00/fdas-induction-outcome-labels.json" \
  --holdout-outcome-label-store "$ROOT/104759-00/fdas-induction-outcome-labels.json" \
  --outcome-target durable-own-unit-city-coverage/8-turn/1.0 \
  --ledger artifacts/freeciv/fdas-delayed-induction-population-live-160-v1/delayed-holdout-ledger.json \
  --output docs/freeciv/evidence/fdas-pr24-delayed-induction-holdout-engine.json \
  --require-engine-source --require-horizon --require-proposal
```

The expected exit code is `1`, because the scientific proposal requirement is
intentionally unmet.
