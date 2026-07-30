# GDO-7B grounded research evidence

## Claim boundary

GDO-7B implements a shadow-only, decision-safe research-selection model and
persistent enabling operation. It does not claim a FreeCiv score improvement,
does not have policy authority, and does not infer that selecting a research
target immediately grants the technology.

The runtime flag `pressure_research_operations_enabled` is default-off and
requires the complete grounded-operation stack:

- PF-v2 semantics;
- packet and identity-resource scheduling;
- RequirementSets;
- grounded domain estimates;
- exact commit revalidation;
- persistent operation lifecycle.

## Grounded interface

`ResearchOptionState` retains each server-advertised technology ID and cost in
the immutable authoritative snapshot. The canonical executable action remains
unchanged and excludes proxy-only cost metadata. Research option metadata:

- participates in snapshot identity;
- is exposed in grounded event context schema `1.4`;
- is consumed by the proof scheduler through the typed snapshot rather than
  rereading raw `legal_actions`;
- records a diagnostic when the server omits cost.

## Dependency semantics

The only propagation mode is
`decomposed_ruleset_dependency_graph`. The canonical `DependencyOracle`
provides:

- the transitive missing prerequisite set;
- the currently researchable frontier;
- chain depth;
- a stable proof hash.

Legacy `tech_want` is not read, copied, or propagated. An advertised research
action outside the strategic target's current dependency frontier abstains.
Long-term strategic target identity remains separate from the immediate
technology selection.

## Switching and completion boundary

For the current research target, ETA uses authoritative progress, cost, and
net beakers per turn under an explicit constant-rate assumption.

For a switch, the target's advertised cost is grounded, but exact switch loss
is unresolved because snapshot v1 does not expose:

- `researching_saved`;
- `bulbs_researching_saved`;
- saved bulbs for the target technology;
- `free_bulbs`.

The model therefore emits an ETA interval and the observed current progress at
risk. It does not translate or reimplement upstream switch-penalty code.

The operation lifecycle has two separate steps:

1. select the currently advertised research target;
2. observe the technology in a later authoritative snapshot.

Learning an intermediate prerequisite completes that operation and requests
replanning, but it does not release the downstream strategic operation.
Only authoritative observation of the strategic target releases the
downstream dependency.

## Synthetic mechanism diagnostic

Run:

```bash
python3 scripts/run_gdo_research_replay.py
```

Artifact:

`benchmarks/gdo/gdo7b_research_grounding_diagnostic.json`

The deterministic diagnostic contains 60 chain/frontier regimes, three
advertised actions per regime, and ten full repeated estimate sets.

| Metric | Immediate simpler baseline | Grounded GDO-7B |
| --- | ---: | ---: |
| Advertised candidates | 180 | 180 |
| Admitted candidates | 180 | 60 |
| False frontier admissions | 120 | 0 |
| Frontier precision | 0.3333 | 1.0000 |
| Frontier recall | 1.0000 | 1.0000 |
| Immediate technology-completion claims | not represented | 0 |
| Legacy `tech_want` applications | not represented | 0 |
| Explicitly unresolved switch-history cases | not represented | 30 |

Observed diagnostic latency:

- mean: `1.2649 ms` per candidate;
- p95: `1.9341 ms` per candidate;
- samples: `180`.

Repeatability:

- ten repeated estimate sets were byte-equivalent after canonicalization;
- semantic report hash:
  `dbf1ecc62477c26b0e53adba76c822109eab3442c20753b117b566d67c4bad92`;
- estimate-set hash:
  `6ba8735021f47895e99e2db4d09d3702532b9bf40885c0a986e82e042dbf7ebc`;
- artifact SHA-256:
  `ff66ae00073585ccb672da5fba3293d2cd3239840c0e8dc495f83297e240cf29`.

This passes the synthetic mechanism gate: candidate precision improves without
frontier recall loss, immediate completion remains impossible, and only one
dependency propagation mode is active.

## Tests

Focused validation:

```text
73 passed in 16.87s
```

Coverage includes:

- immutable option cost and snapshot identity;
- canonical action byte preservation;
- dependency frontier extraction;
- same-target and switch ETA bounds;
- off-frontier abstention;
- one-slot RequirementSet/resource claims;
- selection no-effect detection;
- beaker-stall block and recovery;
- prerequisite-completion replan;
- strategic-completion downstream release;
- default-off runtime gating.

## Open confirmation gate

Before any authority or gameplay-benefit claim, run a fresh engine-backed
cohort that captures research options and operation lifecycle events. It must
show:

- no off-frontier selection admitted by the grounded readout;
- no double propagation through legacy `tech_want`;
- zero research-slot over-allocation;
- no increase in stalled research;
- no regression in technology acquisition or score against the frozen
  comparator.

Until that disjoint confirmation exists, GDO-7B remains a semantic and
decision-safety result only.
