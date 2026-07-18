# Phase 2 / M0 acceptance evidence

Date: 2026-07-17  
Repository base: `6cdef3936552dd7c2f37eabb157ae4bb41c95119` plus the recorded working-tree implementation  
Ruleset source: FreeCiv checkout `26ba7124249f34fd3050ef29bf191bd4d8808018`  
Compiler: `freeciv-ruleset-compiler/1.0`  
Sample seed: `20260717`

## Commands

```bash
export FREECIV_RULESET_ROOT=/path/to/pinned/freeciv/data
for ruleset in civ2civ3 classic; do
  python3 scripts/freeciv/compile_ruleset.py \
    --ruleset-root "$FREECIV_RULESET_ROOT" \
    --ruleset "$ruleset" \
    --out "build/freeciv/rulesets-v2/$ruleset" \
    --event-log "artifacts/freeciv/$ruleset-compile-events-v2.jsonl"
done
FREECIV_RULESET_ROOT="$FREECIV_RULESET_ROOT" \
  pytest -q Autotests/test_freeciv_rulesets.py Autotests/test_freeciv_events.py \
  Autotests/test_freeciv_agent_foundation.py
git diff --check
git check-ignore build/freeciv/rulesets-v2/classic/ruleset.metta
```

Result: 36 tests passed. Both compiler event logs validate under event schema v1. Generated output
is ignored, both rulesets take the same code path, and deliberately injecting an unknown
requirement kind fails with file, line, section, field, and reason.

## Independent audit

The audit module shares secfile lexical parsing but none of the compiler's rule construction.

| Ruleset | Tech targets | Unit targets | Building targets | All targets | Requirement edges | Mismatches |
|---|---:|---:|---:|---:|---:|---:|
| civ2civ3 | 87 | 56 | 73 | 216 | 317 | 0 |
| classic | 87 | 53 | 69 | 209 | 292 | 0 |

For each ruleset, deterministic samples of 20 techs and 20 units have exact antecedent equality.
All rules carry crisp TV `<1.0, 0.99>`. The IR distinguishes `has-tech`, `researchable`,
`buildable`, `has-building`, and `usable-action`. Obsolescence and quantitative metadata remain
separate from prerequisites. The generated conclusion scan finds no numeric accumulation.

## Determinism and hashes

Two fresh CLI runs are compared byte-for-byte for every output in the test suite. Recorded v2
output hashes:

| Output | civ2civ3 SHA-256 | classic SHA-256 |
|---|---|---|
| `ruleset.ir.json` | `c7306b497f156462bd45b330186746a2304aadcc61bd05679c72fe36c1acadfd` | `76ed1542729137d930bbabd8e559ee344df607449007194bd61570724d095788` |
| `ruleset.metta` | `73b7a33242ada1188accbeaa7eb546cb76f8d8d68034ae276c8412206774d277` | `d2a22fa80df3bb44542bc2edb2977f56b39cb65b68496392e1628a9409f135a2` |
| `audit.json` | `960e3d7dd66dc36930360212fa0d7a95ec9436b18ce4dea3a166cdbc80d20628` | `f54df66ac410ffffa9df6d9a3f85bf307078c83ba47766faed3498087140713b` |
| `manifest.json` | `858c5a3f9c56efb5c45acaacf1472806c86f6a355c988059975eec5273074629` | `8765d4a52a2d823d3c92aa4777139225fec93e77061052330f5386b17d928af2` |

Source file hashes and all remaining output hashes are inside each generated manifest. The legacy
`benchmarks/freeciv/rules.metta` handwritten game rulebase has been removed; the repository scan
test permits no replacement handwritten implications in the FreeCiv benchmark tree.
