# FreeCiv engine parity

FreeCiv is the authority for dependency, state, and action legality. The Python
compiler/oracle is never used to manufacture its own expected engine answers.

## Dependency parity

The tracked native adapter in `scripts/freeciv/native` is built against the pinned
FreeCiv source. It loads the selected ruleset and calls FreeCiv's
`research_goal_step`, `research_goal_unknown_techs`, and `research_goal_tech_req`
paths directly. Run the complete hard gate with:

```bash
scripts/freeciv/build_native_parity_image.sh \
  "$FREECIV_LLM_ROOT/freeciv/freeciv" freeciv-research-parity:local
python3 scripts/freeciv/run_engine_parity.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" --ruleset civ2civ3 \
  --states 50 --seed 20260717 \
  --out artifacts/freeciv/m1-parity/civ2civ3-parity.json
python3 scripts/freeciv/run_engine_parity.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" --ruleset classic \
  --states 50 --seed 20260717 \
  --out artifacts/freeciv/m1-parity/classic-parity.json
python3 scripts/freeciv/run_oracle_properties.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" --pairs 100 --seed 20260717
```

The release threshold is 4,350 comparisons and zero mismatches for each ruleset.
A mismatch is a release blocker; preserve its seed/state fixture and do not weaken
the comparator. Accepted results and hashes are recorded in
[Phase 3 evidence](evidence/phase-3-m1.md).

## Authoritative state and action parity

The state comparator reads the patched proxy's `pln_authoritative` DTO, replaces
the local snapshot transactionally, compares every own-state atom and grounded
value, and sends only an action advertised for that same snapshot:

```bash
python3 scripts/freeciv/run_live_state_parity.py \
  --ws-url "$FREECIV_PROXY_WS" --api-token "$FREECIV_API_TOKEN" \
  --game-id pln-state-parity --agent-id pln-state-parity --port 6001 \
  --turns 100 --seed 613 \
  --events artifacts/freeciv/state-parity/events.jsonl
```

Use a dedicated port in 6001-6009. Success requires 100 matched turns, no state or
grounded-value mismatch, no engine rejection, and local rejection of deliberately
replayed prior-snapshot actions. See [Phase 4 evidence](evidence/phase-4-m2.md).

## Performance and failure policy

Oracle performance excludes compiler/import startup. Run:

```bash
python3 scripts/freeciv/benchmark_oracle.py \
  --ruleset-root "$FREECIV_RULESET_ROOT" --ruleset civ2civ3 --rounds 5
```

The accepted warm maximum is 90.18 ms and the regression ceiling is 180.36 ms,
which remains below the 500 ms absolute budget. Timeout, native adapter failure,
unavailable ruleset packets, or incomplete state is a typed failure and blocks
planning/execution; none is converted to an empty successful result.
