# FDAS PR86b isolated-launch paired replacement result

Date: 2026-08-04

Status: accepted engine-backed mechanism evidence; every progression criterion
passed; no score, win-rate, calibrated transition-value, or general policy
claim.

## Execution and integrity

The corrected V3 cohort completed all 32 fixed arms from clean source commit
`b98013c2634b6da439fe267ff90e9982ba7dcaac` in 1,459.95 seconds. Four process
workers used explicit ports 6001–6004, with eight arms per port and serial arm
order inside every seed pair. The run recorded:

- 32 completed arms, zero infrastructure failures, and zero launcher failures;
- 1,182,995 event records across 32 warning-free valid ledgers;
- zero rejected engine actions in every arm;
- all 16 preregistered arm orders reproduced exactly;
- matching grounded logical candidate surfaces in all 16 pairs; and
- one clean source commit and implementation identity across the cohort.

The launch preflight compiled the pinned `civ2civ3` ruleset with compiler 2.0
to IR hash
`81edd60186c3b3fd048ef1fd3cb566667ab9a025d4e11d15ad689f5930ddd03b`,
confirmed the `fciv-net` container and proxy, and confirmed exact
`qwen3-coder-next:latest` availability before creating the output root.

The immutable artifact root is
`artifacts/freeciv/fdas-pr86b-isolated-launch-paired-v3`. Its digest over sorted
relative-path `sha256sum` rows is
`ccff58248d5f21a5cc593b3d11a265f84b61f46627fcc5364351b4781ec5c551`.

## Mechanical result

The deterministic audit accepted every gate. Pair classification was:

| Classification | Pairs |
|---|---:|
| Matched observed | 6 |
| Matched censored | 1 |
| No opportunity | 9 |
| Opportunity mismatch | 0 |
| Outcome mismatch | 0 |
| Incomplete | 0 |

Every grounded opportunity selected the same logical tuple at the same turn
in both arms. The treatment completed all seven assigned replacement
operations, including the pair censored by the fixed horizon. Its 48 bounded
operation attempts were all accepted by the engine. There were no unexplained
assigned-actor removals and no treatment excess in unexplained removal.

The censored pair, seed 110183, assigned at turn 131 and completed treatment at
turn 134, but its fixed 32-turn outcome was due after the 160-turn horizon. It
is excluded from every outcome estimate without imputing a value.

## Paired descriptive outcomes

Among the six matched observed pairs:

| Endpoint (treatment minus control) | Estimate | Paired interval |
|---|---:|---:|
| Both cities retained, risk difference | +0.1667 | [0.0000, 0.5000] |
| City-retention count | +0.3333 | [0.0000, 0.6667] |
| Defended-city count | +0.1667 | [0.0000, 0.5000] |
| Assigned-actor survival count | +0.1667 | [0.0000, 0.5000] |
| Exact combat-attributed actor losses | -0.1667 | [-0.5000, 0.0000] |

The primary binary endpoint had three both-win pairs, two both-lose pairs, one
treatment-only win, and no control-only win. Its exact two-sided McNemar
`p=1.0`. Seed 110323 was the treatment-only primary win: treatment retained
both cities while control retained one. Seed 110233 improved retained cities,
defended cities, actor survival, and exact combat losses, but neither arm
retained both cities, so it was concordant on the primary binary endpoint.
The other four observed pairs were aggregate ties.

All preregistered progression checks passed: at least four observed pairs, at
least two treatment completions, no mechanical failure, no excess unexplained
removal, and a nonnegative city-retention point estimate.

## Interpretation

PR86b resolves the earlier semantic/mechanical bottleneck: logical candidate
selection is pair-stable, bounded replacement execution completes reliably,
and the resulting direction is favorable on every aggregate endpoint in this
small opportunity population. This is meaningful evidence that the corrected
replacement mechanism can improve a consequential city-retention outcome.

It is not evidence of a statistically reliable general improvement. Only six
pairs contributed observed outcomes, there was one primary discordance, the
primary interval includes zero, and McNemar `p=1.0`. Nine of 16 pairs never
formed an eligible intention, so the result also says nothing about most game
states. A later claim-bearing study must first improve or stratify opportunity
yield and use a fresh, powered paired population without changing this frozen
result.

## Reproducibility

The machine report is
`fdas-pr86b-isolated-launch-paired-replacement.json`. A complete second audit
was byte-identical. Both files had SHA-256
`7b88cc4d3c0740758d2395e1ed93551d84265d9b0a7164de98deba7c6eb879da`
and report structural hash
`c2196e639365357b434cdff91d68d3e306cc4744b0011f27930670309ad7d752`.
