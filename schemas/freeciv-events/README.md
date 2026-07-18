# PLN-FreeCiv event schemas

`v1/envelope.schema.json` is the stable transport envelope.
`v1/payloads.schema.json` defines every known event payload and shared proof/plan/atom
structures. JSON Schema draft 2020-12 is authoritative.

## Compatibility

- Every event carries `schema_version`.
- Within major version 1, optional additive payload fields require a schema update and a
  default-preserving fold change.
- Removing, renaming, narrowing, or changing the meaning of a field requires a new major
  schema directory and an explicit replay migration.
- A reader validates the envelope of an unknown future event, preserves its payload, and
  renders raw JSON. It must never silently discard it.
- Events are ordered by `(turn, seq)`. Wall-clock timestamp is descriptive only.
- `caused_by` parents must precede their child in an append-only stream.

## Generated TypeScript

Generate or check the tracked TypeScript definitions with:

```bash
python3 scripts/freeciv/generate_event_types.py
python3 scripts/freeciv/generate_event_types.py --check
```

The UI additionally performs AJV runtime validation against these exact schemas. The
generated file is a compile-time convenience and is not an alternative schema source.

## Validation and fixtures

```bash
python3 scripts/freeciv/generate_synthetic_log.py --all --out artifacts/freeciv/v0-synthetic
python3 scripts/freeciv/validate_events.py artifacts/freeciv/v0-synthetic/normal-crisp.jsonl
```

Good and deliberately corrupt fixtures are deterministic. Seeded corruption diagnostics
are part of the V0 contract.

