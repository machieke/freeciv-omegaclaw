# ADR 0005: JSON Schema is the event wire source of truth

- Status: accepted
- Date: 2026-07-17
- Decision owner: PLN-FreeCiv implementation
- Applies to: V0-V5 and all agent event emitters

## Context

The agent is Python and the observability application is TypeScript. Hand-maintained DTOs
would allow payload, nullability, and version semantics to drift across runtimes.

## Decision

JSON Schema draft 2020-12 is authoritative for manifests and FreeCiv events. Python uses
`jsonschema`; TypeScript uses AJV for runtime validation and generated TypeScript types for
compile-time ergonomics. Generated types are never edited manually.

Known event payloads validate strictly. Unknown future event types retain a valid common
envelope and raw payload so an older UI never drops them silently. Breaking changes require
a new schema version and explicit fold migration.

## Consequences

- Schema changes land before emitter/UI changes.
- CI validates shared fixtures in both runtimes.
- Generated files record generator/version and can be regenerated from one command.

## Reversal condition

Supersede only if one alternative interface definition can generate draft-compatible
runtime validators and types for both languages without losing unknown-event behavior.

