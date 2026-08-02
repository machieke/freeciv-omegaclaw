# FDAS PR22 held-out induction gate evidence

Date: 2026-08-02

Status: lifecycle mechanism accepted; live discovery gate rejected because the
engine population has no outcome contrast

## Scope

This increment operationalizes the Phase 9 train/holdout lifecycle without
granting an induced rule runtime authority. Multiple durable
`DecisionEpisodeStore` artifacts can be combined into deterministic training
and holdout partitions only when their source identities, content digests,
episode IDs, and causal provenance are disjoint.

The bounded miner first persists every candidate in quarantine. Each candidate
then receives a deterministic out-of-sample replay verdict. A promoted verdict
is illegal without a versioned `InductionPromotionApproval` bound to the exact
proposal, validation result, episode partitions, and distinct artifact hashes.
The approval explicitly grants neither policy nor readout authority. Demotions
are persisted without approval. An empty ledger is also persisted, so zero
candidates cannot be confused with a missing run.

Component fixtures prove the positive and negative lifecycle paths: a stable
correlation is promoted with approvals, a reversed holdout is demoted without
approvals, repeat evaluation is idempotent, and overlapping partitions fail
closed. Those fixtures are synthetic mechanism tests, not live discovery
evidence.

## Engine population and frozen split

Four clean-source 160-turn engine games were collected from commit
`4c31f88f6013885d49c156f9fd1ac50d3ac51960`, implementation SHA-256
`88939f653010cedbe4cd5a473f7ad0c78a1868044e3bdf1968e7880436f41681`.
Three reached the full horizon and form the frozen analysis population:

| Partition | Seed | Attributable episodes | Goal relief | Other eligible outcome |
| --- | ---: | ---: | ---: | ---: |
| Training | 4543804 | 5 | 5 | 0 |
| Training | 104743 | 5 | 5 | 0 |
| Holdout | 104759 | 7 | 7 | 0 |
| **Total** |  | **17** | **17** | **0** |

All three event ledgers are source-clean, horizon-complete, schema-valid, and
warning-free. They contain 79,202 events in total. Every encoded episode has
independent execution and immutable-episode provenance and remains
`truth_mutated=false`, `policy_authority=false`.

The fourth game, seed `104761`, completed before the configured horizon and is
excluded from the frozen split. Its three attributable episodes were also all
goal relief; it does not change the diagnosis.

## Strict result

The held-out runner at clean commit
`361de168665fe8d0e0b1714b20f0f7d0e95b3821`, implementation SHA-256
`251d4eab782511221858c37e810933c9301a12948d2ff11bd3a6113dfc253493`,
and runner SHA-256
`bc2d7e46128889280290aeac83ef6f80c3ab42d289f8b48e66b5c807abaeb1cb`
was invoked with clean engine source, full horizon, and a nonzero proposal as
mandatory gates.

Nine of ten checks passed:

- source partitions are nonempty, clean, disjoint, and horizon-complete;
- all three event ledgers validate without errors or warnings;
- the empty ledger is durable and hash-bound;
- every candidate would require a held-out verdict and every promotion a
  versioned approval;
- truth, policy, and readout authority remain false;
- no proposal, validation, promotion, demotion, or approval was fabricated.

`proposal_requirement_met` failed. With 17 positive outcomes and zero
negative outcomes, every tile feature has no defensible contextual residual
against the population baseline. `PatternMiner` therefore returned
`no-pattern-cleared-residual-gate`, zero candidates, and zero promotions. The
strict runner exited nonzero as designed. The empty ledger state hash is
`9494d084d6bb3b8190f3c3d30933e0d2dfa2b3ea7e16566c4e9e24c97aa809e8`.

The machine-readable rejected report is
[`fdas-pr22-induction-holdout-engine.json`](fdas-pr22-induction-holdout-engine.json),
with structural hash
`22fad0d15cb2384bd0518573d2fc4a8b37f7b9872092ab286f41bcd9ddbceba1`.

## Reproduction

```bash
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_fdas_induction_holdout.py \
  --training-store artifacts/freeciv/fdas-induction-population-live-160-v1/games/main/e_full_loop/4543804-00/fdas-decision-episodes.json \
  --training-store artifacts/freeciv/fdas-induction-population-live-160-v1/games/main/e_full_loop/104743-00/fdas-decision-episodes.json \
  --holdout-store artifacts/freeciv/fdas-induction-population-live-160-v1/games/main/e_full_loop/104759-00/fdas-decision-episodes.json \
  --ledger artifacts/freeciv/fdas-induction-population-live-160-v1/fdas-pr22-heldout-ledger.json \
  --output /tmp/fdas-pr22-induction-holdout-engine.json \
  --require-engine-source --require-horizon --require-proposal
```

Exit status 1 is the expected scientific result for this frozen population.

## Diagnosis and next gate

The problem is not insufficient runtime alone. The bounded fortification
authority selects only a current legal fortify action whose immediate success
predicate is also the recorded goal relief. Once an episode remains
attributable, that target is nearly deterministic by construction; actor loss
is conservatively classified as confounded and cannot be relabeled negative.
Collecting more identical episodes is therefore unlikely to create a useful
contrast.

The next induction experiment needs a non-tautological delayed target, such as
durable garrison coverage or city survival after a declared observation
window, plus causal features that generalize across games rather than raw tile
IDs. It must collect naturally occurring attributable relief and no-relief
outcomes under a predeclared split. Until then, held-out promotion and induced
rule readout remain `component-only`, disabled, and empirically unaccepted.

This result provides no discovery-quality, action-selection, score,
gameplay-improvement, or win-rate claim.
