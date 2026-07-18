# Crisp dependency oracle

`freeciv_agent.oracle.DependencyOracle` is the long-lived M1 service selected by ADR 0002. It
indexes the canonical M0 IR once and exposes `deps(Goal, CrispStateView) -> QueryResult`. It never
parses reasoner stdout and never converts a failure to an empty successful result.

A result is `PROVED`, `BLOCKED`, `UNREACHABLE`, or `ERROR`. It contains a structurally deduplicated
AND/OR proof DAG, exact crisp TVs, rule and source identity, grounded results, a typed unsatisfied
frontier, the complete engine-style prerequisite set, latency, depth, tree size, and cache status.
Cycles become finite typed leaves. A timeout or closed service returns a structured error and sets
`executable` false.

```python
from freeciv_agent.oracle import CrispStateView, DependencyOracle, Goal

oracle = DependencyOracle(compiled_ir)
state = CrispStateView("snapshot-id", known_techs={"Alphabet"}, player="player-1")
result = oracle.deps(Goal.researchable("player-1", "Writing"), state)
```

`emit_deps` writes causally linked `pln_query` and `pln_result` events. The event log is lossless;
the UI is not expected to repeat inference.

The native parity executable is built with `scripts/freeciv/build_native_parity_image.sh`. Its C
source calls FreeCiv's `research_goal_*` functions after loading the chosen ruleset through the
engine's own ruleset loader. It accepts deterministic state lines on stdin and returns JSONL.
It is an audit oracle only and is never used for live decisions.

```bash
scripts/freeciv/build_native_parity_image.sh /path/to/pinned/freeciv \
  freeciv-research-parity:local
python3 scripts/freeciv/run_engine_parity.py \
  --ruleset-root /path/to/pinned/freeciv/data \
  --out artifacts/freeciv/m1-parity
```
