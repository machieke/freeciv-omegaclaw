# Freeciv Algorithm Licensing Boundary

Status: active implementation control
Repository license: MIT
Upstream Freeciv license: GPLv2
Grounded-program review basis: `87f3482e631b0713378e69b350e460d4c6a310b7`

## Boundary

OmegaClaw may independently implement behavior derived from public game rules,
protocol-visible authoritative state, and repository-owned ruleset IR. It may
also compare results with a separately installed Freeciv executable through a
black-box subprocess test harness.

The MIT repository must not contain copied or mechanically translated Freeciv
implementation code, implementation comments, or other GPL expression. A
native parity executable, if introduced, remains a separately installed and
distributed component pending an explicit licensing decision.

## Clean-room implementation record

| Domain | Permitted basis | Intended implementation | Native comparison | Status |
|---|---|---|---|---|
| Transition envelope | OmegaClaw types and authoritative snapshot contracts | Repository-owned Python | None | In progress |
| Movement | Public rules, ruleset IR, visible map/unit state | Independent shortest-path implementation | Separately installed Freeciv subprocess | Not started |
| Combat | Public rules, ruleset IR, visible unit/city state | Independent probability implementation | Separately installed Freeciv subprocess | Not started |
| Production | Ruleset IR and authoritative city state | Independent deterministic estimator | Optional black-box fixture comparison | Not started |
| Transport | Public transport rules and visible actor/capacity state | Independent operation estimator | Optional black-box fixture comparison | Not started |

Generated parity fixtures must contain factual inputs and outputs only, be
reviewed for redistributability, and record the generator/version that produced
them.

## Provenance controls

- Every estimator records an ID, version, ruleset digest, and provenance.
- Unsupported rule interactions abstain instead of importing an upstream
  implementation.
- Any future native helper must be invoked across a process boundary and
  documented before use.
- Reviews must reject patches whose source provenance cannot be explained.

## Review sign-off

Technical boundary owner: pending
Licensing reviewer: pending before movement/combat parity merges
Last updated: 2026-07-30
