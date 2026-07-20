"""M0 FreeCiv secfile parser, compiler, and independent-audit tests."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from freeciv_agent.events.validator import validate_file  # noqa: E402
from freeciv_agent.rulesets.audit import audit  # noqa: E402
from freeciv_agent.rulesets.compiler import CompileError, compile_ruleset  # noqa: E402
from freeciv_agent.rulesets.secfile import SecTable, SecfileError, parse  # noqa: E402


def _external_root():
    configured = os.environ.get("FREECIV_RULESET_ROOT")
    candidates = [configured] if configured else []
    candidates.append(os.path.abspath(os.path.join(REPO, "..", "..", "..", "Repos",
                                                   "freeciv-llm", "freeciv", "freeciv", "data")))
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "civ2civ3", "techs.ruleset")):
            return candidate
    pytest.skip("set FREECIV_RULESET_ROOT to run pinned-ruleset integration checks")


def test_secfile_parser_handles_comments_translation_continuation_optional_and_empty_tables():
    content = '''[item]\nname = _("?kind:Display") ; inline comment\nflags = "a",\n        "b"\nreqs =\n { "type", "name", "range", "present"\n   "Tech", "Alphabet", "Player"\n   "MinSize", 3, "City", FALSE\n }\nempty =\n { "type", "name", "range"\n }\n'''
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "fixture.ruleset")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        document = parse(path)
    section = document.sections[0]
    assert section.fields["name"].value == "?kind:Display"
    assert section.fields["flags"].value == ["a", "b"]
    table = section.fields["reqs"].value
    assert isinstance(table, SecTable)
    assert table.dictionaries() == [
        {"type": "Tech", "name": "Alphabet", "range": "Player", "present": None},
        {"type": "MinSize", "name": 3, "range": "City", "present": False},
    ]
    assert section.fields["empty"].value.rows == ()


def test_secfile_parser_rejects_malformed_table_with_source_line():
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "bad.ruleset")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('[x]\nreqs =\n { "type", "name"\n   "Tech", "A", "Player"\n }\n')
        with pytest.raises(SecfileError) as error:
            parse(path)
    assert ":4:" in str(error.value) and "columns" in str(error.value)


@pytest.mark.parametrize("ruleset", ["civ2civ3", "classic"])
def test_pinned_rulesets_compile_with_exact_independent_target_edge_and_sample_parity(ruleset):
    root = _external_root()
    ir = compile_ruleset(root, ruleset)
    result = audit(ir, root, sample_seed=20260717, sample_size=20)
    assert result["passed"], result
    assert not result["missing_targets"] and not result["extra_targets"]
    assert not result["missing_edges"] and not result["extra_edges"]
    assert len(result["samples"]["tech"]) == 20
    assert len(result["samples"]["unit"]) == 20
    assert not result["sample_mismatches"]
    assert not result["trait_mismatches"]
    assert all(rule.tv == {"strength": 1.0, "confidence": 0.99} for rule in ir.rules)
    assert all(rule.target_predicate in ("researchable", "buildable") for rule in ir.rules)
    assert {item["name"] for item in ir.predicate_catalog} >= {
        "has-tech", "researchable", "buildable", "has-building", "usable-action"
    }
    settlers = next(rule for rule in ir.rules
                    if rule.target_kind == "unit" and rule.display_name == "Settlers")
    assert "Cities" in settlers.traits["flags"]["values"]
    assert settlers.traits["flags"]["source"]["file"] == (
        ruleset + "/units.ruleset")
    nonfounders = {"Migrants", "Workers", "Engineers"}
    for rule in ir.rules:
        if rule.target_kind == "unit" and rule.display_name in nonfounders:
            assert "Settlers" in rule.traits["flags"]["values"]
            assert "Cities" not in rule.traits["flags"]["values"]


def test_independent_audit_detects_compiled_unit_trait_drift():
    root = _external_root()
    ir = compile_ruleset(root, "civ2civ3")
    rules = []
    for rule in ir.rules:
        if rule.target_kind == "unit" and rule.display_name == "Settlers":
            traits = dict(rule.traits)
            flags = dict(traits["flags"])
            flags["values"] = [value for value in flags["values"] if value != "Cities"]
            traits["flags"] = flags
            rule = replace(rule, traits=traits)
        rules.append(rule)
    report = audit(replace(ir, rules=tuple(rules)), root)
    assert not report["passed"]
    assert report["trait_mismatches"][0]["target"] == ["unit", "Settlers"]


def test_unsupported_requirement_fails_loudly_with_file_section_field_and_reason():
    root = _external_root()
    with tempfile.TemporaryDirectory() as directory:
        destination = os.path.join(directory, "classic")
        shutil.copytree(os.path.join(root, "classic"), destination)
        units = os.path.join(destination, "units.ruleset")
        text = open(units, encoding="utf-8").read()
        text = text.replace('"Tech", "Pottery", "Player"',
                            '"UnsupportedKind", "Pottery", "Player"', 1)
        with open(units, "w", encoding="utf-8") as handle:
            handle.write(text)
        with pytest.raises(CompileError) as error:
            compile_ruleset(directory, "classic")
    message = str(error.value)
    assert "classic/units.ruleset:" in message
    assert "[unit_worker]" in message and "reqs" in message
    assert "unsupported requirement kind UnsupportedKind" in message


def test_two_clean_cli_runs_are_byte_identical_and_emit_valid_event():
    root = _external_root()
    script = os.path.join(REPO, "scripts", "freeciv", "compile_ruleset.py")
    with tempfile.TemporaryDirectory() as directory:
        outputs = []
        for index in (1, 2):
            out = os.path.join(directory, "run{}".format(index))
            event = os.path.join(directory, "event{}.jsonl".format(index))
            proc = subprocess.run([
                sys.executable, script, "--ruleset-root", root, "--ruleset", "classic",
                "--out", out, "--event-log", event,
            ], cwd=REPO, text=True, capture_output=True, timeout=30)
            assert proc.returncode == 0, proc.stderr
            assert validate_file(event).valid
            outputs.append(out)
        names = sorted(os.listdir(outputs[0]))
        assert names == sorted(os.listdir(outputs[1]))
        for name in names:
            assert open(os.path.join(outputs[0], name), "rb").read() == open(
                os.path.join(outputs[1], name), "rb").read(), name
        ir = json.load(open(os.path.join(outputs[0], "ruleset.ir.json"), encoding="utf-8"))
        assert not any(rule["target"]["predicate"] in {
            "add", "sum", "accumulate", "gold-stockpile", "shield-stockpile"
        } for rule in ir["rules"])


def test_generated_rule_artifacts_are_ignored_and_no_handwritten_game_rulebase_remains():
    ignored = subprocess.run(["git", "check-ignore", "build/freeciv/rulesets/classic/ruleset.metta"],
                             cwd=REPO, text=True, capture_output=True)
    assert ignored.returncode == 0
    tracked = subprocess.run(["git", "ls-files", "benchmarks/freeciv/*.metta"], cwd=REPO,
                             text=True, capture_output=True, check=True).stdout.splitlines()
    tracked = [relative for relative in tracked if os.path.isfile(os.path.join(REPO, relative))]
    assert "benchmarks/freeciv/rules.metta" not in tracked
    for relative in tracked:
        content = open(os.path.join(REPO, relative), encoding="utf-8").read()
        assert "(Implication" not in content, relative
