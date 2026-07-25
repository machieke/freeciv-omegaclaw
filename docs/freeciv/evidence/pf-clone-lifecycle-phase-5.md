# PF-PLN Phase 5 latent-clone lifecycle acceptance

Status: complete; live profile enablement remains opt-in

Implementation commit: `b01d6c6`

Phase 5 persists clone sets, lineage forwarding, applied event IDs, and
transaction history. Each visible atom is updated under a serialized lock and
written by durable atomic replacement. Reopening the store validates clone
identity, posterior normalization, and the configured per-atom cap.

Bayesian updates, splits, and merges are idempotent by event ID. Splits must
preserve the parent's posterior mass and pass predictive-gain, complexity,
split-score, and cap gates. Merges must preserve combined mass and pass truth,
pressure, and successor-distribution similarity gates.

Retired references resolve transitively. The acceptance fixture splits `root`
into `left` and `right`, merges both into `merged`, reopens the persisted
store, and verifies that the original `root` reference resolves to `merged`.
A second split at the two-clone cap fails closed.

Expected visible pressure remains the posterior-weighted mixture. A declared
tail mass additionally produces component-wise worst-tail pressure for
safety-sensitive scheduling; the fixture's 20% danger clone has act pressure
9.0, yielding expected pressure 2.6 and 20%-tail pressure 9.0.

## Exact hidden-context ablation

The deterministic benchmark models two indistinguishable visible states with
different hidden intents. The observation signal is 90% accurate. The action
matched to the hidden intent succeeds with probability 0.9; the mismatched
action succeeds with probability 0.1.

- clone-free expected planning success: 0.50;
- clone-conditioned expected planning success: 0.82;
- absolute improvement: +0.32;
- relative improvement: 64%;
- clone-free mean hidden-context log likelihood: -0.693147 nats;
- clone-conditioned mean log likelihood: -0.325083 nats;
- log-likelihood improvement: +0.368064 nats;
- persisted posterior after the attack signal: attack 0.90, transit 0.10;
- persistence reopen matched exactly.

The benchmark structural artifact hash is
`4727d34d54c625e0f42dfdd47e5d752510bb388304c4916165559d94a5f63a61`.
The rendered artifact SHA-256 is
`a3ed2a5fa2c832e0953c192d9cbceeebe11c7e06cce31aafab33256ed816defd`.
Machine-readable evidence is in
[`pf-clone-lifecycle-phase-5.json`](pf-clone-lifecycle-phase-5.json).

## Regression acceptance

Validation completed with:

- 296 passing Python FreeCiv tests;
- 73 focused pressure, belief, and event tests;
- passing deterministic benchmark and clean diff check.

The observability contract did not change in this phase; the Phase 3
TypeScript typecheck, 20 UI tests, fixture validation, boundary audit, and
production build remain the latest UI acceptance.

## Reproduction

```bash
PYTHONPATH=src python3 scripts/freeciv/run_pf_clone_benchmark.py \
  --out artifacts/freeciv/pf-clone-phase-5.json
```

```bash
pytest -q Autotests/test_freeciv_*.py
```

This exact synthetic ablation establishes the lifecycle mechanism's hidden
context benefit under its declared model. It is not an engine-backed gameplay
score or win-rate claim.
