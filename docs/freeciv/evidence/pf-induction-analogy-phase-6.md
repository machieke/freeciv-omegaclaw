# PF-PLN Phase 6: induction and analogy acceptance

Date: 2026-07-25 UTC

Implementation commit:
`3cfa688138f388ce445b8a7f8f9747d53c1a83ad`

Evidence artifact:
[pf-induction-analogy-phase-6.json](pf-induction-analogy-phase-6.json),
structural hash
`a15472781c85c6d917eb35f53827bfd5d93128db9d66e5e593dee0731b5e629e`.

## Implemented boundary

Phase 6 now has a quarantined, pressure-gated rule lifecycle:

1. the bounded miner finds repeated feature conjunctions only within an exact
   opponent/ruleset/era/geometry/diplomacy context;
2. every candidate carries its complete training-population and observation
   provenance, trigger factors, transfer uncertainty, and context;
3. contextual generalization and structural analogy produce new quarantined
   candidates rather than executable facts;
4. an `expand`-mode operation is materialized only when expansion pressure and
   expected validation value clear the declared validation cost;
5. replay rejects training/validation episode or provenance overlap and
   promotes only out-of-sample Brier and calibration improvements whose
   contradiction rate does not increase; and
6. the atomic lifecycle ledger exposes only replay-promoted rules. Proposal and
   validation transitions emit strict `rule_proposed` and `rule_validated`
   events.

Implied similarity uses the incoming/outgoing relational-profile kernel. It
requires exact context agreement, explicit structural correspondence,
provenance, and transfer reliability. Surface resemblance alone cannot create
a transfer.

## Deterministic replay

Command:

```bash
python3 scripts/freeciv/run_pf_induction_benchmark.py \
  --out docs/freeciv/evidence/pf-induction-analogy-phase-6.json
```

The benchmark uses no random sampling. It mines 64 training episodes per
context, validates the scoped rule on 256 disjoint held-out episodes, and
replays a context-dropped candidate on 384 disjoint episodes spanning two
supporting and four counterexample opponents. Reversing validation episode
order produces the identical validation artifact.

The scoped `border-road AND military-spike -> attack-within-six` candidate:

- was promoted with 64 held-out activations;
- reduced Brier score from `0.187557` to `0.050531`, an absolute improvement
  of `0.137027`;
- reduced activated-rule calibration error from `0.742424` to `0.055556`, an
  absolute improvement of `0.686869`;
- reduced log loss from `0.562486` to `0.237665`; and
- changed contradiction rate from `0.25` to `0.0`.

The opponent-generalized candidate was demoted. On its counterexample replay,
Brier score worsened by `0.100089`, calibration error worsened by `0.561497`,
and contradiction rate increased from `0.083333` to `0.166667`.

The expansion ablation rejects the same candidate at zero `expand` pressure
and materializes its diagnostic validation operation at pressure `1.0`.

## Verification

Focused:

```bash
pytest -q Autotests/test_freeciv_pressure_induction.py
# 7 passed
```

Repository regression:

```bash
pytest -q Autotests/test_freeciv_*.py
# 303 passed

cd apps/freeciv-observability
npm test -- --run
# 20 tests passed; fixtures, boundaries, typecheck, and production build passed
```

The generated TypeScript event contract also passes:

```bash
python3 scripts/freeciv/generate_event_types.py --check
```

The benchmark is a deterministic host-side validation of the Phase 6 semantic
exit criterion. It is not an engine-backed gameplay score or win-rate claim.
