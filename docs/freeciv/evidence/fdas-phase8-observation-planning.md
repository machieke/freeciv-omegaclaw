# FDAS Phase 8 decision-safe observation planning evidence

Status: engine shadow-live in a dedicated profile, no action authority.

The existing value-of-information planner now has a hard decision-eligibility
boundary. A test is omitted—not merely ranked last—when decision sensitivity,
expected information gain, success probability, feasibility, or deadline fit
is zero. Thus generic uncertainty cannot consume observation resources unless
an outcome can change a declared bounded decision.

Engine-live observation planning declares two indivisible packet costs per
operation: one CPU packet plus one observation or simulation packet. The new
packet decision path feeds the pressure scores and operations to the existing
whole-packet scheduler. A high-value simulation with no simulation capacity
does not strand or partially consume CPU; a lower-value feasible observation
may use the intact CPU+observation pair. No CPU capacity means no selection.

Selection records are created before execution and distinguish committed from
uncommitted tests. Evidence still crosses the separate
`ObservationEvidenceGate` only after a selected authoritative return. Model
identity, version/hash, validity scope, inexact confidence cap, selection
propensity, and evidence-overlap discount remain serialized in the operation
and resulting evidence path. Neither pressure nor packet scheduling revises a
belief.

Coverage is in `Autotests/test_freeciv_observation_live.py` and
`Autotests/test_freeciv_fdas_observation_live.py` together with the existing
belief, pressure, and packet scheduler suites. Fresh engine evidence and the
remaining authority boundary are documented in
[`fdas-pr18-observation-pressure-shadow.md`](fdas-pr18-observation-pressure-shadow.md).
The later non-authorizing execution continuation is documented in
[`fdas-pr20-observation-return.md`](fdas-pr20-observation-return.md): selected
visibility tests bind to exact legacy-selected moves and register evidence only
after a fresh authoritative return, while unprovable returns are censored.
