# Phase 3 / M1 acceptance evidence

Date: 2026-07-17  
Ruleset/engine source commit: `26ba7124249f34fd3050ef29bf191bd4d8808018`  
Native parity image: `sha256:d1e29fc9ee9f0555e904c52bd78dd837da5f941033fff4437cb0155648d242f2`  
Random seed: `20260717`  
Host profile: x86_64, Python 3.8.10; native build/runtime: Ubuntu Noble, Meson 1.3.2, release build

## Native engine parity hard gate

Commands:

```bash
scripts/freeciv/build_native_parity_image.sh /path/to/pinned/freeciv \
  freeciv-research-parity:local
python3 scripts/freeciv/run_engine_parity.py \
  --ruleset-root /path/to/pinned/freeciv/data \
  --states 50 --seed 20260717 --out artifacts/freeciv/m1-parity
python3 scripts/freeciv/run_oracle_properties.py \
  --ruleset-root /path/to/pinned/freeciv/data --pairs 100 --seed 20260717
```

The C adapter loads the ruleset with FreeCiv and directly calls `research_goal_step`,
`research_goal_unknown_techs`, and `research_goal_tech_req`. The compiler source is not used to
produce the expected answer.

| Ruleset | Technologies | Random states | Comparisons | Mismatches |
|---|---:|---:|---:|---:|
| civ2civ3 | 87 | 50 | 4,350 | 0 |
| classic | 87 | 50 | 4,350 | 0 |

Parity artifact SHA-256:

- civ2civ3: `63cfc3c726858abaebf230603679facf2e32aacf115988d78530d588e01c7f30`
- classic: `932938adb7e53625d45a53cf18bb13f8ca14378d773b63cc27cfdaf5ddb109d9`

The 100-pair amended leaf property ran 269 native checks with zero failures. Each reported
frontier leaf was immediately engine-researchable; filling the full prerequisite set unlocked the
goal; removing each direct predecessor from that filled state blocked it.

## Proof and failure behavior

The focused M0/M1/V0 suite passed 29 tests. Synthetic cycle, diamond, and OR graphs terminate and
retain every branch. A diamond stores its shared subtree once while both parents reference it.
Every node and atom retains TV `<1.0, 0.99>`. Disabled/missing targets return `UNREACHABLE` and a
typed frontier. Zero-timeout and closed-service tests return `ERROR`, emit a schema-valid failure
event, and set `executable = false`.

Real proof/result events include source rules, complete deduplicated DAGs, formulas, frontier,
latency, depth, tree size, and cache status. Their causal chain validates from result to query to
invoker. TypeScript/AJV validation remained green after the additive v1 schema extension.

Native adapter source hash: `10a82f06287b8d9810a6397d0e6ef65357fdbc3c5be0b19bbae542f17a8d7498`.

## Performance

Command:

```bash
python3 scripts/freeciv/benchmark_oracle.py \
  --ruleset-root /path/to/pinned/freeciv/data --ruleset civ2civ3 --rounds 5
```

Compiler/import startup was outside the hot path. Across 435 cache-miss proofs: p50 8.93 ms,
p95 32.53 ms, p99 54.58 ms, maximum 90.18 ms. The longest measured chain was Environmentalism at
depth 12, 132 proof nodes, and 23.94 ms. This establishes a 90.18 ms accepted maximum baseline;
the CI regression limit is 180.36 ms (2x), still below the 500 ms absolute acceptance limit.
