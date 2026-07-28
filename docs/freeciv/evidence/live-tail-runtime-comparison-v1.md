# Live event-tail 480-turn runtime comparison

Date: 2026-07-28

The observability application default Live endpoint is
`ws://127.0.0.1:18765`. This avoids the unrelated HTTP service occupying port
8765 on the validation host.

## Design

Both arms used:

- `profile/freeciv_harness_480_turn.yaml`;
- seed `4543804`;
- condition `e_full_loop`;
- one engine-live worker;
- the same pinned proxy, FreeCiv, ruleset, and `qwen3-coder-next:latest`;
- a deliberately unloaded Ollama model before each arm, so both runs exercised
  `complete_chat` readiness rather than giving the second arm a warm-model
  advantage.

The treatment started `serve_event_tail.py` on port 18765 before the event file
existed. A real Chromium session subscribed through the Live UI before the
harness started and remained connected through turn 480. The control had no
tail process, browser, or subscriber. `/usr/bin/time` measured the complete
harness command in each arm.

## Results

| Measurement | Active Live tail | No tail | Tail minus control |
|---|---:|---:|---:|
| Harness wall time | 261.13 s | 273.38 s | -12.25 s (-4.48%) |
| Engine backend | 248.167 s | 262.127 s | -13.960 s (-5.33%) |
| Engine gameplay | 197.952 s | 212.633 s | -14.681 s (-6.90%) |
| Model readiness | 49.720 s | 48.955 s | +0.765 s (+1.56%) |
| Wall time less readiness | 211.410 s | 224.425 s | -13.015 s (-5.80%) |

This single matched pair shows no end-to-end runtime regression from active
Live observability on this eight-core host. The treatment being faster must not
be interpreted as a performance improvement: ordinary engine and process
scheduling variance is larger than the observed difference, and one pair
cannot estimate a runtime distribution.

The tail is nevertheless computationally inefficient. Point samples during
the treatment showed the tail process rising from approximately 47% to 64% of
one CPU core as the append-only trace grew from 18 MB to 30 MB. The current
tail rescans and schema-validates the complete file for each batch. Spare host
cores prevented that extra work from becoming wall-clock delay in this run,
but the result does not establish safety on a CPU-constrained or concurrent
host.

## Equivalence checks

Both arms had:

- manifest identity
  `9ce7850dc243556dd2bd78c45dd3dde42f274d5bf27290b01cc0565d8690a046`;
- configuration hash
  `5dea1a05c2874af88a73187274c11ef3674ad413b1df8edcac8a8e54c9edd8e9`;
- 8,890 canonical events and 728 engine actions;
- identical ordered action payloads
  (`a415cc5755d6bcc345ea0b944351af2f9feb632152df69f0b273c1d971e595b5`);
- identical authoritative snapshot payloads
  (`03bec046db67bd3e3da5cc00343af5f217c34d470010127ee0be5338207fd525`);
- identical terminal score metrics
  (`9bc6502434f4c544eab858fc7f55e9ff8703eaa09b4f333c3ffabab8c4afcdfe`);
- score 319, opponent score 2,412, score gain 216, and zero rejected
  actions.

The raw JSONL hashes differ as expected because event IDs, causal IDs,
timestamps, and latency samples are run-specific.

Both JSONL files passed the canonical event validator. The treatment also
passed `browser-event-fold-equivalence/1.0` at all 481 terminal turn cursors
with zero divergences between incremental Live folding and a fresh replay.

## UI verification

The observability gate passed strict type checking, validation of 140 fixture
events, boundary checks, 36 unit tests, and a production build. ProofShot
verified the default endpoint, a subscription made before the event file
existed, live progress, and the terminal turn-480 cursor. The browser reported
zero console errors and the development server reported zero errors.
