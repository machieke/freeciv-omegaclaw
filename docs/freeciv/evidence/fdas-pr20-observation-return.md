# FDAS PR20 legacy-bound observation-return evidence

Date: 2026-08-02

## Scope

This increment closes the non-authorizing execution/return continuation of the
PR18 observation-pressure slice. A packet-committed visibility test may bind
only to the byte-identical legal `unit_move` already selected by the legacy
controller. The binding records the current snapshot, source sequence,
legal-action digest, packet schedule, outcome catalog, and selection record;
all of them are revalidated immediately before action materialization.

The bridge cannot choose or replace an action. Its only truth-bearing return
is a fresh authoritative player-visibility delta after the accepted move. It
does not infer enemy absence, and the checked default profile remains disabled.

## Return firewall

The live causal path is:

```text
legacy-selected legal unit_move
  -> decision-sensitive visibility test and atomic CPU/observation packets
  -> exact action binding and commit revalidation
  -> accepted engine action and fresh authoritative snapshot
  -> packet_returned
       -> authoritative visibility outcome -> selected EvidenceToken
       -> or censored no-write abstention
  -> fresh FDAS revision only after evidence registration
```

An authoritative evidence return requires the same game/player identity, a
strictly newer source sequence, the actor at the declared endpoint, and one of
the two predeclared outcomes: `visibility-expanded` or
`no-visibility-expansion`. The resulting selection-adjusted token enters the
belief store through `ObservationEvidenceGate`; planning itself preserves both
the evidence count and evidence-store hash.

FreeCiv may accept a move and remove the actor before the next observable
snapshot. Treating that case as a negative visibility result would fabricate
evidence. PR20 therefore records a typed
`actor-removed-before-observation-proof` or `action-endpoint-not-reached`
abstention. Its before/after evidence counters must be equal, and it has no
truth mutation or policy authority.

## Fresh engine-backed cohort

The predeclared, claim-ineligible cohort
`fdas_observation_execution_shadow_diagnostic_v1` ran both arms for 30 turns on
seed `173205` with fog of war enabled. It used clean source commit
`eea9e53bcfc34b9ee19678508b13c1cc531687e1`, implementation SHA-256
`681ba9fee7dcd26dc8d5a5fe0170cefc49cc04aea4df94e7605670bb5aec9c54`,
and cohort configuration hash
`144ee3a54d2cccfb10927d0d6e594e564561559fe7ce25f7bef689ca9ed2feba`.

| Measure | Baseline | Treatment | Total |
| --- | ---: | ---: | ---: |
| Horizon reached | yes | yes | 2/2 |
| Engine actions / accepted results / rejects | 78 / 78 / 0 | 71 / 71 / 0 | 149 / 149 / 0 |
| Exact bindings and commit revalidations | 40 | 32 | 72 |
| Authoritative evidence returns | 38 | 32 | 70 |
| Censored no-write returns | 2 | 0 | 2 |
| Visibility-expanded outcomes | 27 | 28 | 55 |
| No-visibility-expansion outcomes | 11 | 4 | 15 |
| FDAS/policy authority actions | 0 | 0 | 0 |
| Event-schema errors / warnings | 0 / 0 | 0 / 0 | 0 / 0 |

Every binding has exactly one accepted-action return: either a causally linked
evidence token and observation event or an explicit no-write abstention. The
status counters match the event inventory, both event streams validate with no
warnings, source freeze passed, and the paired run had no infrastructure
failure. The deterministic audit structural hash is
`bc846133d3b65d4998a5699027156f8a7ffed7e4937f6620e0d26748103ec7e1`;
the report is
[`fdas-pr20-observation-return-engine.json`](fdas-pr20-observation-return-engine.json).

## Verification

The focused component and audit tests pass 11 checks. The broader FDAS config,
harness, execution, and return suite passes 152 checks. The engine artifacts
are reproducible with:

```bash
FREECIV_FDAS_CONFIG_PATH=profile/dependent_atomspace_observation_execution_shadow.yaml \
FREECIV_FDAS_MANIFEST_PATH=profile/fdas_manifest_observation_execution_shadow.json \
PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/run_impact_evaluation.py \
  --config profile/freeciv_harness.yaml \
  --out artifacts/freeciv/fdas-observation-return-live-30-v3 \
  --backend engine-live --workers 1 --server-ports 6001 \
  --cohort fdas_observation_execution_shadow_diagnostic_v1 --no-resume

PYTHONPATH=src:benchmarks \
python3 scripts/freeciv/audit_fdas_observation_return_live.py \
  --cohort-root artifacts/freeciv/fdas-observation-return-live-30-v3 \
  --output docs/freeciv/evidence/fdas-pr20-observation-return-engine.json
```

The environment must also supply the existing FreeCiv proxy URL/WebSocket,
server container, ruleset root, Ollama OpenAI-compatible base URL, and API
token.

## Claim boundary and continuation

This proves the fail-closed observation execution and evidence-return mechanism
for a visibility-frontier test attached to legacy-selected movement. It does
not prove that FDAS selects better scouting actions, that visibility results
establish opponent absence, or that the mechanism improves score or win rate.
The opponent-presence PR18 test also remains a planning-only model; PR20 does
not relabel a visibility frontier delta as direct opponent-presence evidence.

PR21 subsequently exercised a live contradictory independent lineage and
complete context quarantine without authority leakage; see
[`fdas-pr21-belief-conflict.md`](fdas-pr21-belief-conflict.md). That diagnostic
uses an intentionally false capped prior and does not turn PR20's visibility
delta into opponent-presence or absence evidence. Broader decision gaps and
any FDAS-selected observation action require their own calibrated transition
model, legal-action safety evidence, and explicit activation gate.
