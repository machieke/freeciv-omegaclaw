# FDAS PR86b ruleset preflight correction

Date: 2026-08-04

PR86b repeats the exact V3 cohort, including its 16 seeds, SHA-256 arm order,
profiles, four workers, ports 6001–6004, 160-turn horizon, endpoints, and all
acceptance and progression criteria. The first PR86 root is excluded because
all arms failed before an event ledger or game configuration existed.

The corrected launcher adds fail-closed runtime dependency validation before
creating the output root. The run binds the pinned local ruleset path:

```text
FREECIV_RULESET_ROOT=/home/purplezky/Repos/freeciv-llm/freeciv/freeciv/data
```

It also validates the running `fciv-net` container, the default local proxy,
the local Ollama endpoint, and exact `qwen3-coder-next:latest` availability.
The launch manifest records only non-secret dependency identities; the API
token is neither inspected nor persisted. Per-arm launch results now include
the exact infrastructure error when a harness arm fails.

The fresh corrected output root is
`artifacts/freeciv/fdas-pr86b-isolated-launch-paired-v3`. It must not exist at
preflight, and the failed PR86 root remains immutable. The scientific claim
boundary remains the claim-ineligible descriptive mechanism scope registered
in `fdas-pr86-isolated-launch-paired-replacement-preregistration.md`.
