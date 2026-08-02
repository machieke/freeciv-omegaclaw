# FDAS PR21 belief-conflict and quarantine evidence

Date: 2026-08-02

## Scope

This increment closes the Phase 8 live contradiction gate without granting
FDAS any policy authority. A dedicated diagnostic profile inserts one capped,
non-exact model prior for the generic proposition `opponent-present(any)`.
The prior is installed before the engine adapter reads the public player
roster. A later player-visible roster packet supplies positive evidence for
the same proposition through the ordinary `BeliefStore` revision path.

The diagnostic prior is intentionally false when an opponent is present. Its
purpose is to exercise the epistemic safety mechanism, not to claim a useful
opponent model. The two observations declare independent source lineages:

- `simulator-model:*` for the capped diagnostic prior;
- `player-visible-roster-packet:*` for the engine observation.

Different evidence-token identifiers from one declared source lineage cannot
manufacture a conflict. Source lineage is now a first-class field on evidence,
observation, conflict, and projected lineage records.

## Conflict and quarantine contract

When both independent revisions pass the manifest-bound confidence and
severity gates, `BeliefStore` creates one `ConflictAtom` with the exact left
and right evidence and source lineages. The live adapter emits that conflict
once, partitions all declared belief contexts, and emits one
`context_quarantine` per context. Every quarantine directly cites the conflict
event; a merely transitive citation through another quarantine is rejected by
both event validation and the audit.

FDAS then rematerializes the same immutable game snapshot and projects:

- the uncertain opponent proposition and its current revision;
- both evidence and source lineages;
- the conflict target and conflict lineages;
- each retained/excluded context partition and quarantine relation.

All projected propositions remain `crisp: false`. Conflict and quarantine
records are diagnostic/control knowledge only. The profile and capability
manifest explicitly set policy authority and every domain authority to false.

## Fresh engine-backed cohort

The predeclared, claim-ineligible cohort
`fdas_belief_conflict_shadow_diagnostic_v1` ran both arms for 30 turns on seed
`161803`. It used clean source commit
`2463fd2d7a22fb791fca90d18fe964818fa4393f`, implementation SHA-256
`338366e5aceb60df04986ed5126434a479da3c7a98c6b31b6e26c22c783c5d0f`,
and cohort configuration hash
`7e4601fa0879b6e8c5bd6a62df356cf6367f3bb372b90fb32c0e1e63f6a9bf8a`.

| Measure | Baseline | Treatment | Total |
| --- | ---: | ---: | ---: |
| Horizon reached | yes | yes | 2/2 |
| Engine actions / accepted results / rejects | 62 / 62 / 0 | 52 / 52 / 0 | 114 / 114 / 0 |
| Capped model priors | 1 | 1 | 2 |
| Player-visible roster revisions | 1 | 1 | 2 |
| Independent-source conflicts | 1 | 1 | 2 |
| Complete context quarantines | 2 | 2 | 4 |
| FDAS / operation authority actions | 0 / 0 | 0 / 0 | 0 / 0 |
| Event-schema errors / warnings | 0 / 0 | 0 / 0 | 0 / 0 |

The baseline ledger contains 1,557 events and the treatment ledger 1,480.
Both validate with zero errors and zero warnings. Terminal counters match the
event inventory, both arms pass every mechanism audit check, source freeze is
clean and stable, and the cohort has no infrastructure failures. The audit's
deterministic structural hash is
`4d0a1b65fbdfabd9d87852f42c4a198d1c4a53dddd92e6772e6c6baf6817fb87`;
the report is
[`fdas-pr21-belief-conflict-engine.json`](fdas-pr21-belief-conflict-engine.json).

## Hardening trail

Three rejected attempts materially tightened the final evidence contract:

1. The first run exposed that observation-event validation did not yet admit
   the already-typed model `validity_scope`; the schema and generated client
   contract were corrected.
2. A tech-bearing-unit trigger produced no conflict because no qualifying unit
   became player-visible before the prior decayed. The diagnostic was replaced
   by the public-roster proposition so its trigger is grounded and reliable.
3. The next run formed both conflicts and all quarantines, but final validation
   rejected the second quarantine because it cited the first quarantine rather
   than the conflict directly. The emitter and audit now require direct causal
   citations for every partition.

Only the fourth, clean-source run is accepted evidence.

## Reproduction

```bash
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_belief_conflict_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_belief_conflict_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_impact_evaluation.py \
  --config profile/freeciv_harness.yaml \
  --out artifacts/freeciv/fdas-belief-conflict-live-30-v4 \
  --backend engine-live --workers 1 --server-ports 6001 \
  --cohort fdas_belief_conflict_shadow_diagnostic_v1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_belief_conflict_live.py \
  --cohort-root artifacts/freeciv/fdas-belief-conflict-live-30-v4 \
  --output docs/freeciv/evidence/fdas-pr21-belief-conflict-engine.json
```

The environment must also provide the existing FreeCiv proxy URL/WebSocket,
server container, ruleset root, Ollama OpenAI-compatible base URL, and API
token.

## Claim boundary

This is live mechanism evidence for independent source-lineage conflict,
complete context quarantine, causal projection, and zero authority leakage.
The diagnostic prior is deliberately synthetic. The result does not establish
model accuracy, opponent absence, calibrated uncertainty, better action
selection, score improvement, or win-rate impact. Any action authority that
uses uncertain beliefs remains a separate bounded activation and acceptance
gate.
