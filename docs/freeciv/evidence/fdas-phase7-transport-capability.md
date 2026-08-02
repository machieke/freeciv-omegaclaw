# FDAS Phase 7 transport capability projection

Status: component-only, shadow-only, no policy authority.

This increment adds one bounded `transport` scope for each owned unit with an
unambiguous compiler-backed unit profile and positive transport capacity. It
projects:

- the exact carrier unit and accepted cargo classes;
- current cargo compatibility and founder compatibility from compiled unit
  classes and flags;
- authoritative carried-by relations from `transported` and `transported_by`;
- current available/full status when the authoritative own-unit transport
  relation set is complete and yields an exact derived `cargo_count`;
- the same typed `transport_seat` `ResourceRef` used by
  `ResourceCapacityExtractor` and the exact resource scheduler;
- a current embark or disembark edge only when the action is server-advertised
  and the carrier binding is unique.

Unknown load omits both available and full claims. A full carrier does not
receive an embark edge even if an inconsistent synthetic action advertises
one. Multiple compatible carriers at the embark tile are treated as ambiguous
and no edge is emitted. The load transition from available to full is checked
for incremental/cold equivalence.

The projected resource atom is a capacity identity, not a reservation. Actual
double-claim rejection remains the responsibility of the existing bounded
exact scheduler; the shared `ResourceRef` identity makes the two layers agree
on which seat is contested.

Boundaries of this increment:

- it does not assemble or activate a multimodal operation;
- it does not estimate rendezvous or delivery ETA;
- it does not infer a carrier from proximity when more than one compatible
  carrier exists;
- it does not model escort safety or fleet defense;
- no FDAS authority flag is enabled.

Verification:

```text
pytest -q Autotests/test_freeciv_fdas_transport.py \
  Autotests/test_freeciv_fdas_dependencies.py \
  Autotests/test_freeciv_fdas_phase0.py \
  Autotests/test_freeciv_transport_operations.py

30 passed
```

Semantic correction: FreeCiv's packet `carrying` field identifies trade goods
and is never used as passenger load. Passenger count is derived from complete
`transported`/`transported_by` relationships; incomplete relationships fail
closed. This correction is covered by empty, loaded, full, contradictory, and
incomplete-relation regressions.
