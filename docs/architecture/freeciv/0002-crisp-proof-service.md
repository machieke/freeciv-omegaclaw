# ADR 0002: Use the canonical IR for the crisp proof service

- Status: accepted
- Date: 2026-07-17
- Decision owner: PLN-FreeCiv implementation
- Applies to: M1 and the crisp portion of PLN observability

## Context

The existing bridge starts `/PeTTa/run.sh` for every query and regex-extracts a
recommendation. The image's PeTTa runtime is a batch SWI-Prolog program: it loads one
file, prints evaluation results, and halts. It exposes neither a long-lived structured
proof API nor the lossless proof nodes needed by V2. The current bridge also hides
runtime errors as an empty successful result.

M1 requires deterministic AND/OR proofs, all alternatives, typed blocking frontiers,
cycle detection, native-engine parity, and sub-500 ms warm queries.

## Decision

The ruleset compiler produces one typed canonical IR. The M1 crisp dependency service
executes backward queries directly over that IR in a persistent Python process and emits
structured proof objects. The same compiler emits Atomese/MeTTa as a deterministic,
auditable representation. Tests compare the IR and Atomese manifests, source identities,
rules, and edges so they cannot drift.

PLN remains responsible for uncertain truth-value inference in M4. The M1 crisp service
is the exact dependency portion of the PLN boundary, but it does not invoke a general
truth-value engine for facts that are definitionally crisp.

No handwritten or independently maintained executable rule graph is permitted. Runtime
failure is typed and blocks planning/action execution.

## Consequences

- Warm query latency does not include interpreter startup.
- Proof structure is native data rather than reconstructed from text.
- Engine parity can be debugged at source-rule and edge level.
- The phrase “backward chainer over the M0 rulebase” means the canonical M0 IR and its
  generated Atomese are two outputs of one compiler, with the IR as executable crisp form.
- The agent specification is amended to make this operational boundary explicit.

## Reversal condition

Supersede this ADR if PeTTa gains a stable persistent API that returns the required
structured proofs within the latency budget. It must first pass the same parity and proof
contract tests.

