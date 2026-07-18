# FreeCiv ruleset compiler

The M0 compiler has one data-selected code path for `civ2civ3` and `classic`. It reads the
upstream `techs.ruleset`, `units.ruleset`, and `buildings.ruleset` secfiles and produces canonical
JSON IR, generated MeTTa/Atomese, grounded signatures, an independent audit, and a hash manifest.
Generated output is ignored under `build/freeciv/rulesets/`.

Set the source root to a pinned FreeCiv `data` directory:

```bash
export FREECIV_RULESET_ROOT=/path/to/pinned/freeciv/data
python3 scripts/freeciv/compile_ruleset.py \
  --ruleset civ2civ3 \
  --out build/freeciv/rulesets/civ2civ3 \
  --event-log artifacts/freeciv/civ2civ3-compile-events.jsonl
```

The parser accepts sections, comments, quoted and translatable strings, backslash and comma
continuations, vectors/tables, optional table cells, booleans, numeric values, and empty vectors.
The compiler gives each target a stable identity based on `rule_name`, falling back to its
context-stripped display name. All requirements retain their file, line, section, and field.

One implication is emitted per tech, unit, or building target. Its antecedent is the complete
conjunction of requirements. Negative `present` requirements are explicit `Not` atoms. Numeric
costs and rates are metadata or grounded procedure signatures; the generated rulebase contains
no arithmetic accumulation conclusion.

The audit extractor shares only lexical secfile parsing with the compiler. It independently
compares target identities, every prerequisite edge, and deterministic samples of 20 techs and
20 units. An unsupported requirement kind or table column stops compilation and reports logical
file, line, section, field, and reason.

Compiler version `freeciv-ruleset-compiler/1.0` and IR schema version `1.0` are compatibility
boundaries. Any semantic mapping change increments the compiler version and changes output hashes.
