# PR46 corrected-probe candidate-union shadow

## Implementation boundary

PR46 adds corrected forward/backward probes only after the frozen calibrated
candidate union confirmed by PR45. The probe layer builds a bounded factor
graph from the exact advertised legal defense surface and uses importance-
corrected overlap only to enlarge protected candidate membership.

It cannot change scalar scores, the scalar winner, action selection, policy,
readout authority, truth, advection, or capacity allocation. An incomplete
factor graph or unhealthy probe batch returns the calibrated union unchanged.
All graph, batch, selection, signal-ledger, snapshot, revision, and result
identities are emitted in a dedicated `fdas-probe-candidate-union` event.

## Exploratory engine smoke

The claim-ineligible seed `105071` was replayed at 160 turns from source commit
`fa1114cbb6f9da00d52cef3037afa92ff0689363` with an exploratory maximum of
four probe regions. The game completed without infrastructure failure and
reported:

| Measure | Result |
|---|---:|
| probe-union evaluations | 84 |
| candidate readouts | 164 |
| healthy evaluations | 84 |
| incomplete graphs | 0 |
| fallbacks | 0 |
| probe-selected memberships | 137 |
| additions beyond calibrated union | 52 |
| action-selection changes | 0 |

The artifact is
`artifacts/freeciv/fdas-probe-candidate-union-smoke-v1`. It is engineering
evidence only and is excluded from confirmation claims.

## Frozen refinement before confirmation

The exploratory cap selected more regions than required. Re-reading only the
already-emitted reachability readouts, without outcomes or score, showed that
a maximum of one probe region would still have produced 25 additions: 19 at
baseline rank two and 6 at baseline rank three. PR47 therefore freezes the
stricter one-region limit before using any fresh seed.

The `minimum_path_diversity` gate is zero because the backward topology has at
most one direct legal route per candidate and therefore cannot satisfy a
path-count-normalized diversity floor on small choice sets. Diversity remains
measured in each batch. ESS and clipped-weight health gates remain active; an
unhealthy batch still fails closed.

## Claim boundary

This smoke demonstrates executable, deterministic, bounded shadow behavior.
It does not establish candidate quality, counterfactual outcome, gameplay,
score, or win-rate improvement. Only the fresh preregistered PR47 cohort may
support recurrent probe-recall claims.
