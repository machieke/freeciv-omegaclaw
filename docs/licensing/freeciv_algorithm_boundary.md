# Freeciv Algorithm Licensing Boundary

Status: active implementation control
Repository license: MIT
Upstream Freeciv license: GPLv2
Grounded-program review basis: `97ff07b`

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
| Transition envelope | OmegaClaw types and authoritative snapshot contracts | Repository-owned Python | None | Shadow complete |
| Movement | Public rules, ruleset IR, visible map/unit state | Independent bounded one-edge corridor model | Separately installed Freeciv subprocess | Shadow implemented; parity pending |
| Combat | Public rules, ruleset IR, visible unit/city state | Independent bounded finite-duel mathematics | Separately installed Freeciv subprocess | Shadow implemented; parity pending |
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
- `NativeGameplayOracle` and `scripts/run_gdo_gameplay_parity.py` define that
  process boundary. No native gameplay comparator source or binary is
  distributed by this repository.
- Reviews must reject patches whose source provenance cannot be explained.

## Review sign-off

Technical boundary owner: pending
Licensing reviewer: pending before movement/combat parity merges
Last updated: 2026-07-30
