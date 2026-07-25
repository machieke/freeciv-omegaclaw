# PF-PLN Phase 2 provenance and contradiction acceptance

Status: complete

Implementation commit: `4b018a0`

PF-PLN Phase 2 now materializes provenance-distinct disagreement instead of
only returning a scalar severity. The uncertain belief store creates explicit
`Conflict` atoms when both evidence contributions exceed the declared
confidence floor and their conflict severity exceeds the declared threshold.
Both lineages remain immutable and inspectable.

For conflicts whose evidence belongs to distinct contexts, the store
materializes a deterministic operation for each context. Applying an operation
retains the matching lineage and excludes the incompatible lineage only from
that context's belief view. It does not retract either evidence token or alter
the aggregate belief. Forged, incomplete, overlapping, wrong-target, or
noncanonical partitions fail closed.

Uncertain deductions now forward their complete atom/rule ancestry. A
derivation is rejected when the target atom already occurs in that ancestry or
when it tries to derive an atom from its own observation token. This prevents
an uncertain proof path from gaining support by closing a cycle.

## Deterministic adversarial benchmark

The checked benchmark used 64 independently shuffled path orders with 128
paths per order:

- 8,192 correlated duplicate paths replayed;
- exactly one unique token contributed to every result;
- zero evidence-overlap errors;
- zero false conflict atoms;
- 256 of 256 attempted three-edge proof cycles rejected;
- zero proof cycles accepted.

The conflict fixture combined two independent confidence-0.8 observations
with strengths 1.0 and 0.0. It produced severity 0.64 and two deterministic
context operations. The unqualified aggregate strength was 0.5; the selected
context retained one lineage and returned strength 1.0.

The benchmark's structural artifact hash is
`a91a200541260453ee21dd7d61a538a457c0f0938a5b0a530c9792c9ed0f4ea6`.
The rendered artifact SHA-256 is
`b6e030ee97b8dfedb08d793c2a0b5a2900602b4ea97966549dd788eb5293c232`.
Machine-readable evidence is in
[`pf-provenance-contradiction-phase-2.json`](pf-provenance-contradiction-phase-2.json).

## Event and regression acceptance

`belief_conflict` and `context_quarantine` are strict v1 event payloads and
generated TypeScript types. The stream validator requires quarantine
operations to directly cite an earlier conflict event and to partition its
complete provenance lineage. Replay folds conflict atoms without recomputing
their truth or severity.

Validation completed with:

- 284 passing Python FreeCiv tests;
- 20 passing observability unit tests;
- 11 valid UI fixtures containing 140 events;
- zero UI boundary violations;
- passing TypeScript typecheck and production build;
- current generated event types and a clean diff check.

## Reproduction

```bash
PYTHONPATH=src python3 scripts/freeciv/run_pf_provenance_benchmark.py \
  --out artifacts/freeciv/pf-provenance-contradiction-phase-2.json
```

```bash
pytest -q Autotests/test_freeciv_*.py
```

```bash
cd apps/freeciv-observability
npm test
```

This is correctness and containment evidence, not a gameplay score or win-rate
claim. Automatic scheduling of observation work for an active conflict belongs
to Phase 3.
