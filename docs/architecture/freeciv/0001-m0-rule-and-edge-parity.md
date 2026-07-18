# ADR 0001: Compile one target rule and audit prerequisite edges

- Status: accepted
- Date: 2026-07-17
- Decision owner: PLN-FreeCiv implementation
- Applies to: M0

## Context

M0 R0.2 requires one implication per technology/action/building with a conjunctive
antecedent. A0.1 says the number of implications should equal the number of `req1` and
`req2` edges. A technology with two prerequisites makes those literal interpretations
incompatible.

## Decision

The compiler emits one canonical implication per target. Its antecedent contains every
requirement with preserved AND/OR, negation, and scope semantics. An independent audit
extractor compares the complete set of `(target, prerequisite, kind, range, present)`
edges and separately reports target-rule count.

A0.1 is interpreted as prerequisite-edge parity, not implication-count parity. The
functional specification is amended to say this explicitly.

## Consequences

- Proof trees retain target-level conjunctions.
- Rule count and edge count remain independently visible.
- A missing prerequisite cannot be hidden by combining counts.
- Generated output remains deterministic because target and antecedent order are
  canonical.

## Reversal condition

Supersede this ADR only if FreeCiv exposes a rule semantic requiring separate target
implications. The audit must still compare all source edges.

