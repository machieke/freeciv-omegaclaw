# PR54 randomized decision-readout hardening replay preregistration

Status: mechanically stable; preregistered acceptance rejected

Implementation commit: `db11226a20b029d1eff8ed389569ad9053477fa1`

## Purpose and claim boundary

PR54 is a claim-ineligible engineering replay of the four exact PR53b failure
seeds. It tests only whether the full-immutable choice identity, bounded exact
authority reprojection, and incomplete-failure audit corrections eliminate the
observed crashes without weakening legality, outcome linkage, or authority
boundaries. Because all four seeds and their prior failures have been observed,
PR54 cannot contribute to opportunity-yield, candidate-value, score, gameplay,
or win-rate estimation.

## Frozen design

| Input | Value |
|---|---|
| Config | `profile/freeciv_harness_fdas_randomized_hardening_replay_160_turn.yaml` |
| Seeds | `105503`, `105529`, `105557`, `105607` |
| Horizon | 160 turns |
| Backend | `engine-live` |
| Condition | `e_full_loop` only |
| Workers | 4 isolated processes on ports 6001 through 6004 |
| FDAS config | `profile/dependent_atomspace_defense_choice_surface_shadow.yaml` |
| FDAS manifest | `profile/fdas_manifest_defense_alternative_collection_randomized_pilot.json` |
| Assignment policy | `fdas-defense-nearest-score-randomized/4.0`, probability `0.5` |
| Outcome | `durable-selected-actor-city-defense/32-turn/2.0` |
| Audit | `fdas-randomized-alternative-live-audit/1.3` |
| Output | `artifacts/freeciv/fdas-randomized-hardening-replay-v1` |

All PR53b gameplay, assignment, missingness, and authority boundaries remain
unchanged. The source commit must be the clean documentation-only descendant
containing this preregistration, with one implementation digest across games.
The run is created from scratch with `--no-resume`; no PR53b artifact is
modified.

## Acceptance criteria

PR54 passes only if:

1. all four games reach the fixed endpoint with no infrastructure failure and
   zero rejected engine actions;
2. no choice-set identity collision or exact-rematerialization exception
   occurs, including the repeated-selection turn patterns previously observed;
3. every event ledger and persisted store is valid, hash-consistent, and not
   quarantined;
4. every eligible assignment has an exact reconstructed draw and propensity,
   one accepted engine action, one linked episode, one selected choice row,
   and a correctly opened and resolved or administratively censored label;
5. seed `105529` exercises at least one accepted treatment assignment, proving
   the formerly failing broader exact action reaches the downstream execution
   and attribution gates; and
6. no truth, score, claim, flow, advection, capacity, or unrelated action
   authority appears.

Zero-opportunity games remain valid mechanical evidence and are not excluded.
No outcome direction can alter the decision rule. After a pass, the next yield
study must use a new, unobserved seed cohort.

## Frozen result

PR54 ran all four exact historical failure seeds from clean source commit
`2a4c902` with implementation digest
`5f6e888d6208ddb3cea41728d4d1387a4b7c31f1929d87f841dacf16e7235c7d`.
The four games completed the fixed 160-turn endpoint in 683.11 seconds with no
infrastructure failure and zero rejected engine actions. None reproduced the
three choice-set identity collisions or the exact-rematerialization exception.

The replay emitted seven randomized assignments. All seven reconstructed to
their frozen exogenous draws and propensities, executed as accepted actions,
linked to one exact episode and selected choice, and resolved their due-turn
labels. Seed `105557` exercised the repeated-selection pattern with five
assignments, including three treatments. Seed `105529`, however, produced two
control assignments and no treatment. It therefore failed frozen acceptance
criterion 5 even though its formerly crashing turns now completed safely.

The original audit 1.3 generic mechanical gates pass when zero-opportunity games
are allowed: four controls, three treatments, seven observed labels, no overdue
pending labels, and report hash
`8a90addb28ed11d2194a63d14223e00c4e175348a1c34705ef5311ee09b1bb44`.
Audit 1.4 adds seed-scoped gates and correctly rejects the frozen seed-`105529`
treatment requirement; the checked-in report hash is
`09e2326711c360bc9623a234c8635f663f076bf42605acefda35bd8247c07b55`.

This replay remains claim-ineligible. Its raw descriptive outcome was one
positive among four controls and one positive among three treatments, with the
three treatments clustered in one already-selected game. That is neither a
candidate-value estimate nor a gameplay claim. In addition, execution version
1.0 did not record whether exact rematerialization used the cached catalog or
the bounded reprojection fallback. The next engineering retry must use the new
typed `authority_catalog_reprojected` execution provenance and require at least
one accepted observed fallback before unseen-seed yield work resumes.
