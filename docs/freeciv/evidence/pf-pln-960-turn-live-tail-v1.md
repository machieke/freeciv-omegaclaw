# PF-PLN 960-turn live-tail run

Date: 2026-07-28

This is a single-seed exploratory horizon extension, not a statistically
reliable score or win-rate claim.

## Configuration

- Profile: `profile/freeciv_harness_960_turn.yaml`
- Backend: engine-live
- Condition: `e_full_loop`
- Seed: `4543804`
- Ruleset/opponent: `civ2civ3` / built-in experimental AI
- Model: `qwen3-coder-next:latest`
- Event tail: active persisted-first subscriber on
  `ws://127.0.0.1:18765`
- Artifact:
  `artifacts/freeciv/pf-pln-960-turn-live-tail-20260728`

The event tail started before the event file existed. Its subscriber received
the terminal `run_completed` event at turn 960, sequence 2,881.

## Result

| Measurement | Result |
|---|---:|
| Completed turns | 960 / 960 |
| Harness wall time | 444.02 s |
| Engine backend time | 424.604 s |
| Engine gameplay time | 421.839 s |
| Model readiness time | 2.264 s |
| Canonical events | 17,722 |
| Engine actions | 1,195 |
| Meaningful cognitive actions | 235 |
| Rejected actions | 0 |
| Score | 495 |
| Opponent score | 4,431 |
| Score gain from initial state | 392 |

The final authoritative snapshot contained five cities with population 41,
70 known technologies, 28 beakers per turn, and active research on Mass
Production at 198/1,470. Treasury state was 222 gold at -21 per turn with
40/0/60 tax/luxury/science rates. Six units remained, cities 101 and 181 were
garrisoned, and city 127 remained disordered.

## Validation

- canonical event schema: valid, zero errors, zero warnings;
- fixed horizon reached without terminal elimination;
- Live-versus-Replay fold equivalence:
  `browser-event-fold-equivalence/1.0`;
- sampled cursors: 961;
- divergences: 0;
- exact log SHA-256:
  `fae7449b530b97a65e940e538e9865e0124e47cb92fbd58dd3d338d0aa1fd031`;
- final folded-state SHA-256:
  `76b5c9a48f926a54ed9d1a20fd718017d4fef00ebd0ffa4fb38a8fa273acbaeb`.

The active tail approached one full CPU core as the trace grew to 56 MB
because each bounded batch currently rescans and revalidates the complete
file. It remained correct and did not prevent horizon completion, but this is
a measured scalability cost rather than an efficient long-horizon design.
