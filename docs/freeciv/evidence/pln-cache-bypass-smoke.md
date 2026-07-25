# Authoritative cache-bypass smoke

Date: 2026-07-25

Status: focused proxy coverage, one two-seed phase-profile control, two
independent two-seed engine treatments, and a four-trace release audit passed.
This is exact-behavior engineering evidence, not a gameplay score or win-rate
claim.

## Full-turn profile

After conditional state stability was accepted, the harness split each full
turn into cognitive selection, non-terminal actions and authoritative
confirmation, and end-turn submission. The control at
`artifacts/freeciv/full-turn-phase-profile-20260725` measured:

| Full-turn component | Two-seed mean |
|---|---:|
| Complete full turn | 276.2 ms |
| Cognitive phase | 114.0 ms |
| Action and confirmation phase | 146.5 ms |
| End-turn submission | 15.4 ms |

The cognitive mean includes one approximately 5.2-second cold selection call
amortized across 60 measured turns. The second game and later steady turns
spent approximately 28 ms in cognition. Action and confirmation was therefore
the dominant repeatable phase.

## Root cause and change

Every full authoritative response attempted two state-cache inserts:

1. the inner `StateExtractor` cache;
2. the outer WebSocket handler cache.

Each layer serialized and gzip-compressed the projection before discovering
that its approximately 4.2--4.3 KiB compressed representation exceeded the
4 KiB entry limit. Proxy logs showed paired `State too large for cache`
warnings for every full query and no authoritative cache hits.

The larger-cache experiment documented in the lazy-construction smoke was not
reintroduced: authenticated cache hits were slower than projection rebuilds.
Instead, PLN authoritative requests now bypass both ineligible cache lookups
and inserts. Other formats retain their caches. The v4 conditional response is
the exact-turn/source fast path for unchanged authoritative revisions.

## Engine comparison

All cohorts used seeds 104729 and 104743, a serial 30-turn engine topology,
the resident `qwen3-coder-next:latest` model, and identical v4 stability,
planner, observer, score, and event-durability configuration:

- failed-cache-write control:
  `artifacts/freeciv/full-turn-phase-profile-20260725`
- cache-bypass treatment:
  `artifacts/freeciv/pln-cache-bypass-treatment-20260725`
- independent treatment repeat:
  `artifacts/freeciv/pln-cache-bypass-treatment-repeat-20260725`

| Measure (two-seed mean) | Control | Treatment | Repeat |
|---|---:|---:|---:|
| Boundary state gate | 207.0 ms | 195.3 ms (-5.65%) | 197.9 ms (-4.41%) |
| Complete boundary | 218.5 ms | 206.5 ms (-5.49%) | 209.3 ms (-4.19%) |
| Mean turn loop | 496.1 ms | 481.5 ms (-2.94%) | 484.0 ms (-2.45%) |
| Gameplay | 19,033.0 ms | 18,728.0 ms (-1.60%) | 18,701.7 ms (-1.74%) |
| Complete backend | 20,751.0 ms | 20,455.6 ms (-1.42%) | 20,381.5 ms (-1.78%) |

The full-turn profile itself remained stable: cognitive, action/confirmation,
and end-turn means changed by less than 1.6%. The gain is concentrated in
authoritative state construction at turn boundaries, as expected.

## Behavioral acceptance

Control, treatment, and repeat retained, per seed:

- identical initial authoritative fingerprints;
- bit-for-bit canonical action hashes:
  - 104729:
    `3e5da136c5f69d7c700ad80c794c87c0da9a44205dd317c675a7e7d3a874dcf5`;
  - 104743:
    `6c66824aeb87a6ee98be7707da0c53316c279b44def2cae6c9fbbb4eba1de376`;
- scores and margins 107/-2 and 112/-3;
- 48/70 engine actions, 18/40 planned actions, and 17/39 impact actions;
- one/two settlement completions;
- zero rejected actions and zero deferred, expired, pending, or timed-out
  confirmations.

One treatment trace omitted the scheduler-nonconsumed
`initial_enemy_distance` diagnostic because the initial observer packet set
did not contain a distance. It did not change the initial decision
fingerprint, planner inputs, actions, or outcomes.

## Verification

- Complete repository FreeCiv lane: 343 passed.
- Focused patched-proxy lane: 117 passed, 4 skipped.
- Engine comparison: 6/6 games completed without infrastructure failures.
- Four treatment traces passed every release-audit check, including the pinned
  external contract and PF-PLN phase audit.
