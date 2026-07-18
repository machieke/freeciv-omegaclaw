# ADR 0003: Use a native FreeCiv test executable for parity

- Status: accepted
- Date: 2026-07-17
- Decision owner: PLN-FreeCiv implementation
- Applies to: M1-M3 engine truth comparisons

## Context

The proxy reports current invention and city-buildability state, but M1 must compare 50
randomized states for every technology. Reimplementing `research_goal_*` in Python would
compare one reimplementation with another and would not establish engine parity.

FreeCiv exposes `research_goal_step`, `research_goal_unknown_techs`,
`research_goal_bulbs_required`, and `research_goal_tech_req` in its common library.

## Decision

Build a small native test executable from the exact pinned FreeCiv source used by the
server. It loads a selected ruleset through FreeCiv's own ruleset machinery, applies a
serialized randomized research state, calls the native `research_goal_*` functions, and
emits normalized JSON.

The executable is a test/oracle component, never part of live agent decision-making. Its
source is tracked here or in the pinned `freeciv-llm` dependency; its binary is an ignored
build artifact identified by source and image hashes.

If direct library linkage proves unavailable in a supported build, the fallback is a
FreeCiv-owned test binary added to the upstream source tree—not a Python expected-value
implementation.

## Consequences

- The parity job needs a FreeCiv build environment.
- Failures retain seed, ruleset hash, native output, oracle output, and a minimized state.
- Proxy state remains useful for live comparisons but is not the randomized parity oracle.

## Reversal condition

Supersede only if FreeCiv publishes an equivalent versioned test API that can set arbitrary
research states and returns the same native computations.

