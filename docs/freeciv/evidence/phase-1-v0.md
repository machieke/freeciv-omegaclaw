# Phase 1 / V0 acceptance evidence

Date: 2026-07-17  
Base repository commit: `6cdef3936552dd7c2f37eabb157ae4bb41c95119` (working tree intentionally dirty with this implementation)  
Host profile: x86_64, Python 3.8.10, Node 22.20.0, npm 10.9.3  
Schema dependencies: jsonschema 4.23.0, AJV 8.20.0, ajv-formats 3.0.1, TypeScript 5.8.3  
Synthetic configuration: fixed UTC clock, deterministic incrementing event IDs, no random input

## Contract and compatibility

JSON Schema draft 2020-12 in `schemas/freeciv-events/v1` is the wire source of truth.
The generated TypeScript declarations are checked byte-for-byte against the generator. Known
payloads are strict. Unknown future types retain envelope validation, raw payload preservation,
and a stable `W_UNKNOWN_TYPE` diagnostic. Compatibility and breaking-change rules are recorded
in `schemas/freeciv-events/README.md`.

Schema hashes:

- envelope: `d6ce057fe846d082e83e5f36891dbbac82dab88700404fa15026f32bf0b26142`
- payloads: `ed23bd3b843fd5f324105de13f086e8be32b6b8cc526b7de3d76f9fd64ba5384`
- generated TypeScript: `b75cd25ac5e42d28356b6891f84c97dbb51e57473b80368e3eaf714bcb685bd6`

## Verification

Commands:

```bash
pytest -q Autotests/test_freeciv_events.py Autotests/test_freeciv_agent_foundation.py
cd apps/freeciv-observability && npm test && npm audit --audit-level=high
python3 scripts/freeciv/generate_synthetic_log.py --all --overwrite --out artifacts/freeciv/v0-synthetic-v2
/usr/bin/time -f 'elapsed=%e rss_kb=%M' \
  python3 scripts/freeciv/validate_events.py \
  artifacts/freeciv/v0-synthetic-v2/performance-200-turns.jsonl
python3 scripts/freeciv/proof_dedup_report.py --repetitions 40
```

Results:

- Python foundation and event suite: 28 passed (later focused event rerun: 15 passed).
- TypeScript compilation and AJV: 11 fixtures, 140 events, valid; npm audit: 0 findings.
- Six positive causal scenarios validate.
- Each of five corrupt scenarios fails with only its intended leading diagnostic:
  `E_CAUSAL_ACTION_ROOT`, `E_CRISP_TV_DRIFT`, `E_DUPLICATE_PROVENANCE`,
  `E_CONFABULATION_WRITE_THROUGH`, or `E_SEQ_GAP`.
- Concurrent emission preserves 40 unique, contiguous turn-scoped sequences. Resume validates
  the existing prefix before allocating the next sequence.
- Repeated generation is byte-identical and tracked compact fixtures are checked in tests.
- Structural proof hashes ignore node IDs; equivalent subtrees are stored once while every
  parent reference is preserved. The 40-copy report shrank 41 nodes / 16,809 bytes to 2 nodes /
  1,365 bytes (91.88% saved) without changing the proof root hash.

## Performance fixture

The generated trace has 200 turns, 1,001 events, and 50,000 state atoms. It is 8.7 MB total;
the maximum observed turn is 45,660 bytes, well below the 5 MB/turn limit. Streaming validation
completed in 9.70 seconds with 23,944 KB maximum RSS on the recorded host profile. It found no
schema, ordering, parent, proof, or action-ancestry error. Every action is causally reachable to
an allowed proposal or monitor root.

Artifact SHA-256:

`9056120b3e4371dd7384150ab3cfaffe34dacbb83d9f3dfa445130316d7f5165`

The performance artifact is generated and ignored; the command above reproduces it.
