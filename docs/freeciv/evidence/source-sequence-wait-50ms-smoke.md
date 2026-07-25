# Source-sequence wait and 50 ms stability smoke

Date: 2026-07-25

Status: implementation and two-seed engine acceptance passed; engineering
latency evidence only, not a general performance or gameplay claim.

## Change

The v3 proxy contract adds a bounded authoritative-state wait over
`after_source_seq` and `wait_timeout_ms`. Packet notification occurs only after
the packet has been dispatched and stored. The harness uses that wait when it
requires a newer revision, but it still requires two matching decision
fingerprints.

The accepted-action stability interval is separately versioned as
`impact_policy.refresh_stability_interval_seconds`. It was reduced from 200 ms
to 50 ms while retaining:

- a 500 ms whole refresh deadline;
- two matching samples;
- reset-on-change behavior;
- state, visible-enemy, and exact legal-action-digest coverage in the
  stability fingerprint;
- candidate-specific effect checks and deferred reconciliation.

The tracked proxy patch is based on upstream
`26ba7124249f34fd3050ef29bf191bd4d8808018` and has SHA-256
`0c555b0ad9b330420e845af64695866d1f903ea6f8398b0123128d0068e7017f`.

## Engine comparison

Both arms used the same patched proxy, resident model
`qwen3-coder-next:latest`, engine topology, 30-turn horizon, and seeds. The
control was a temporary copy of the release profile with only the stability
interval changed to 200 ms. The tracked treatment used 50 ms.

- Control:
  `artifacts/freeciv/source-seq-wait-200ms-control-20260725`
- Treatment:
  `artifacts/freeciv/source-seq-wait-live-smoke-v4-20260725`

| Seed | Gameplay control (ms) | Gameplay treatment (ms) | Confirmation control (ms) | Confirmation treatment (ms) | Loop control (ms) | Loop treatment (ms) |
|---:|---:|---:|---:|---:|---:|---:|
| 104729 | 42,906.4 | 40,103.0 | 449.5 | 391.7 | 1,274.3 | 1,180.7 |
| 104743 | 41,079.8 | 39,444.4 | 472.9 | 437.0 | 1,225.7 | 1,176.6 |
| Mean | 41,993.1 | 39,773.7 | 461.2 | 414.4 | 1,250.0 | 1,178.7 |

Mean gameplay time fell by 2,219.4 ms (5.29%), mean confirmation latency by
46.8 ms (10.15%), and mean loop latency by 71.3 ms (5.71%). Mean complete
backend time fell from 48,925.3 ms to 46,665.5 ms (4.62%). The first arm in
each run used a complete readiness chat and the second used the resident
keep-alive refresh, keeping readiness ordering matched.

## Behavioral acceptance

For both seeds:

- the canonical action sequence was identical between control and treatment;
- fixed-horizon scores and margins were unchanged (`107/-2` and `109/-6`);
- engine and meaningful-action counts were unchanged (`71/41` and `68/38`);
- deferred/recovered counts were unchanged (`26/26` and `29/29`);
- expirations and rejected actions remained zero;
- each run reached turn 30 with one settlement completion.

Including the legal-action digest in the stability fingerprint was validated
before the final v4 treatment. This closes the earlier gap where state facts
could match while the executable catalog was still changing.

## Verification

- Proxy fresh-apply lane: 112 passed, 4 skipped.
- Mounted proxy authoritative contract lane: 18 passed.
- Focused host policy/transport/harness lane: 130 passed.
- Final targeted state/legal stability assertions: 4 passed.
- Engine comparison: 4/4 arms completed with zero infrastructure failures.

The cohort has only two paired seeds and was selected for engineering
confirmation, not inferential statistics. It supports merging the bounded
latency policy without a gameplay regression claim; it does not establish a
population-wide speedup, score improvement, or win-rate improvement.
