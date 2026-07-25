# Deferred confirmation 300 ms engine smoke

Date: 2026-07-25

Status: implementation and two-seed engine acceptance passed; engineering
latency evidence only, not a general performance or gameplay claim.

## Selection rationale

The accepted 500 ms/50 ms-stability traces were classified by the time from an
accepted impact-action result to the stable state snapshot emitted before the
next action. Across seeds 104729 and 104743:

- 22 same-turn confirmations completed in 123.7--247.8 ms;
- 55 actions produced no same-turn snapshot, consumed the complete 500 ms
  deadline, and recovered through the deferred ledger;
- move, attack, and other unit categories occurred in both groups, so a
  category-specific direct-defer rule was rejected.

The release policy therefore versions a 300 ms deadline. This retains more
than 50 ms of margin above the observed successful maximum while shortening
only the no-update path. The 50 ms two-sample state-and-legal-set stability
gate and deferred reconciliation remain unchanged.

## Engine comparison

Both arms used the same patched proxy, model, topology, 50 ms stability
interval, serial ordering, 30-turn horizon, and seeds. The only configuration
change was `refresh_timeout_seconds` from 0.5 to 0.3.

- 500 ms control:
  `artifacts/freeciv/source-seq-wait-live-smoke-v4-20260725`
- 300 ms treatment:
  `artifacts/freeciv/confirmation-timeout-300ms-live-smoke-20260725`

| Seed | Gameplay 500 ms | Gameplay 300 ms | Confirmation 500 ms | Confirmation 300 ms | Loop 500 ms | Loop 300 ms |
|---:|---:|---:|---:|---:|---:|---:|
| 104729 | 40,103.0 ms | 34,814.8 ms | 391.7 ms | 255.7 ms | 1,180.7 ms | 1,005.8 ms |
| 104743 | 39,444.4 ms | 34,084.9 ms | 437.0 ms | 277.9 ms | 1,176.6 ms | 985.5 ms |
| Mean | 39,773.7 ms | 34,449.8 ms | 414.4 ms | 266.8 ms | 1,178.7 ms | 995.7 ms |

Mean gameplay time fell by 5,323.8 ms (13.39%), mean confirmation latency by
147.6 ms (35.61%), and mean loop latency by 183.0 ms (15.53%). Mean complete
backend time fell from 46,665.5 ms to 41,324.5 ms (11.45%).

## Behavioral acceptance

For both seeds:

- canonical action sequences were identical;
- fixed-horizon scores and margins were unchanged (`107/-2` and `109/-6`);
- engine and meaningful-action counts were unchanged (`71/41` and `68/38`);
- deferred/recovered counts were unchanged (`26/26` and `29/29`);
- expirations and rejected actions remained zero;
- each arm reached turn 30 with the same settlement result.

Both treatment arms completed without infrastructure failure. Focused
configuration and policy bounds passed before the run. The release audit
validates the resulting cognitive traces separately.

## Scope

This is a two-seed engineering cohort selected from timing diagnostics. It
supports the bounded deadline change without a gameplay regression claim. It
does not establish a population-wide latency effect, score improvement, or
win-rate improvement.
