"""Tests for validate_implement_output.py.

Run:
    python scripts/test_validate_implement_output.py
    python -m pytest scripts/test_validate_implement_output.py -v
"""
# tested-by: CONSILIUM-IMPLEMENT-CODER-001
# tested-by: CONSILIUM-IMPLEMENT-TEST-WRITER-001
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import validate_implement_output as vio

ROOT = Path(__file__).parent.parent
SCRIPT = Path(__file__).parent / "validate_implement_output.py"


def coder_out(**over):
    out = {
        "files_written": [
            {"path": "src/calc.py", "purpose": "add", "symbols": ["add"]}],
        "maps_to_criterion": "add() returns the sum",
        "scope_escapes": [],
        "blocked": False,
        "blocked_reason": None,
    }
    out.update(over)
    return out


def writer_out(**over):
    out = {
        "test_files_written": [
            {"path": "tests/test_calc.py", "covers": "add sums"}],
        "tests": [{
            "name": "test_add", "targets_symbol": "add",
            "behavior_pinned": "1+1 == 2", "fails_on_empty_impl": True,
            "why": "empty impl returns None",
        }],
        "uncoverable": [],
    }
    out.update(over)
    return out


def manifest_out(**over):
    out = {
        "spec": {"chosen_approach": {"id": "a"}, "chosen_resolved": True},
        "files_written": [{"path": "src/calc.py", "symbols": ["add"]}],
        "test_files_written": [
            {"path": "tests/test_calc.py", "covers": "add sums"}],
        "gate": {"red_ok": True, "green_ok": True, "gate_passed": True},
        "gate_rejected": [],
        "review": {"verdicts": []},
        "blocked": False,
        "blocked_reason": None,
    }
    out.update(over)
    return out


class TestCoder(unittest.TestCase):
    # verifies: CONSILIUM-IMPLEMENT-CODER-001#AC-1
    def test_well_formed_output_is_valid(self):
        self.assertEqual(vio.validate_coder(coder_out()), [])

    # verifies: CONSILIUM-IMPLEMENT-CODER-001#AC-1
    def test_unblocked_needs_files_and_mapping(self):
        self.assertIn("files_written is empty and not blocked",
                      vio.validate_coder(coder_out(files_written=[])))
        self.assertIn("maps_to_criterion must be non-empty text",
                      vio.validate_coder(coder_out(maps_to_criterion=" ")))

    # verifies: CONSILIUM-IMPLEMENT-CODER-001#AC-2
    def test_blocked_needs_reason_and_no_files(self):
        ok = coder_out(files_written=[], blocked=True,
                       blocked_reason="sketch names no target file")
        self.assertEqual(vio.validate_coder(ok), [])
        no_reason = coder_out(files_written=[], blocked=True)
        self.assertIn("blocked is true but blocked_reason is empty",
                      vio.validate_coder(no_reason))
        wrote = coder_out(blocked=True, blocked_reason="unclear")
        self.assertIn("blocked but files_written is not empty",
                      vio.validate_coder(wrote))

    # verifies: CONSILIUM-IMPLEMENT-CODER-001#AC-3
    def test_scope_escape_must_not_be_written(self):
        clean = coder_out(scope_escapes=["src/other.py"])
        self.assertEqual(vio.validate_coder(clean), [])
        both = coder_out(scope_escapes=["src/calc.py"])
        self.assertIn("src/calc.py is both written and in scope_escapes",
                      vio.validate_coder(both))

    # verifies: CONSILIUM-IMPLEMENT-CODER-001#AC-3
    def test_written_path_must_be_within_files_touched(self):
        out = coder_out()
        self.assertEqual(vio.validate_coder(out, ["src/calc.py"]), [])
        self.assertIn("src/calc.py is outside files_touched",
                      vio.validate_coder(out, ["src/other.py"]))

    def test_paths_compare_across_separators_case_and_dot_prefix(self):
        out = coder_out(files_written=[
            {"path": "SRC\\Calc.py", "purpose": "add", "symbols": ["add"]}])
        self.assertEqual(vio.validate_coder(out, ["./src/calc.py"]), [])
        both = dict(out, scope_escapes=["./src/CALC.py"])
        self.assertTrue(vio.validate_coder(both))

    def test_coder_must_not_write_test_files(self):
        out = coder_out(files_written=[
            {"path": "src/test_calc.py", "purpose": "t", "symbols": ["t"]}])
        self.assertIn("Coder wrote a test file: src/test_calc.py",
                      vio.validate_coder(out))

    def test_malformed_shapes_are_reported_not_raised(self):
        self.assertEqual(vio.validate_coder([]),
                         ["output must be a JSON object"])
        self.assertTrue(vio.validate_coder({"files_written": []})[0]
                        .startswith("missing keys:"))
        bad = coder_out(files_written=[{"path": "a.py"}, "x"],
                        scope_escapes="none")
        problems = vio.validate_coder(bad)
        self.assertIn("files_written[0].purpose must be non-empty text",
                      problems)
        self.assertIn("files_written[1] must be an object", problems)
        self.assertIn("scope_escapes must be a list of paths", problems)


class TestTestWriter(unittest.TestCase):
    # verifies: CONSILIUM-IMPLEMENT-TEST-WRITER-001#AC-1
    def test_well_formed_output_is_valid(self):
        self.assertEqual(vio.validate_test_writer(writer_out()), [])

    # verifies: CONSILIUM-IMPLEMENT-TEST-WRITER-001#AC-1
    def test_every_test_must_fail_on_empty_impl(self):
        out = writer_out(tests=[
            {"name": "test_a", "fails_on_empty_impl": True},
            {"name": "test_b", "fails_on_empty_impl": False},
            {"name": "test_c", "fails_on_empty_impl": "yes"}])
        problems = vio.validate_test_writer(out)
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("fails_on_empty_impl" in p for p in problems))

    # verifies: CONSILIUM-IMPLEMENT-TEST-WRITER-001#AC-1
    def test_test_files_must_exist_and_start_with_test(self):
        self.assertIn("test_files_written is empty",
                      vio.validate_test_writer(
                          writer_out(test_files_written=[])))
        impl = writer_out(test_files_written=[
            {"path": "src/calc.py", "covers": "x"}])
        self.assertIn("test_files_written[0].path must start with test_",
                      vio.validate_test_writer(impl))

    def test_uncoverable_entries_need_a_reason(self):
        ok = writer_out(uncoverable=[
            "needs a live network", {"behavior": "x", "reason": "GUI"}])
        self.assertEqual(vio.validate_test_writer(ok), [])
        bad = writer_out(uncoverable=[{"behavior": "x"}, ""])
        self.assertEqual(len(vio.validate_test_writer(bad)), 2)


class TestManifest(unittest.TestCase):
    def test_passed_gate_is_valid(self):
        self.assertEqual(vio.validate_manifest(manifest_out()), [])

    # verifies: CONSILIUM-IMPLEMENT-TEST-WRITER-001#AC-2
    def test_test_green_under_stub_must_be_in_gate_rejected(self):
        # Reports whether the stub-green tests were rejected; the RED/GREEN
        # measurement itself is verify_red_green's (test_implement_pipeline).
        gate = {"red_ok": False, "green_ok": True, "gate_passed": False}
        silent = manifest_out(gate=gate)
        problems = vio.validate_manifest(silent)
        self.assertIn("gate failed but gate_rejected is empty", problems)
        self.assertIn("a test passed under the stub (red_ok false) but "
                      "gate_rejected is empty", problems)
        reported = manifest_out(gate=gate, gate_rejected=[
            {"test": "test_add", "reason": "green under stub"}])
        self.assertEqual(vio.validate_manifest(reported), [])

    def test_gate_passed_must_agree_with_red_and_green(self):
        gate = {"red_ok": False, "green_ok": True, "gate_passed": True}
        self.assertIn(
            "gate_passed is true but red_ok/green_ok is false",
            vio.validate_manifest(manifest_out(gate=gate)))

    def test_gate_must_be_three_booleans(self):
        self.assertEqual(
            vio.validate_manifest(manifest_out(gate={"gate_passed": True})),
            ["gate needs boolean red_ok, green_ok and gate_passed"])

    def test_blocked_manifest_skips_the_gate_checks(self):
        blocked = manifest_out(blocked=True, blocked_reason="thin sketch",
                               files_written=[], test_files_written=[],
                               gate={})
        self.assertEqual(vio.validate_manifest(blocked), [])
        no_reason = dict(blocked, blocked_reason=None)
        self.assertTrue(vio.validate_manifest(no_reason))

    def test_abort_object_is_a_valid_outcome(self):
        abort = {"error": "subagent_json_invalid", "role": "coder"}
        self.assertEqual(vio.validate_manifest(abort), [])
        self.assertTrue(vio.validate_manifest({"error": ""}))

    def test_manifest_files_need_no_purpose(self):
        out = manifest_out(files_written=[
            {"path": "src/calc.py", "symbols": ["add"]}])
        self.assertEqual(vio.validate_manifest(out), [])


class TestCli(unittest.TestCase):
    def run_cli(self, *args, stdin=""):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), *args],
            input=stdin, capture_output=True, text=True, encoding="utf-8")

    def test_exit_0_on_valid(self):
        res = self.run_cli("--role", "coder", stdin=json.dumps(coder_out()))
        self.assertEqual((res.returncode, res.stdout.strip()),
                         (0, "OK: coder output is well-formed"))

    def test_exit_1_lists_problems(self):
        res = self.run_cli("--role", "coder",
                           stdin=json.dumps(coder_out(files_written=[])))
        self.assertEqual(res.returncode, 1)
        self.assertIn("files_written is empty and not blocked", res.stdout)

    def test_exit_2_on_malformed_json_and_bad_args(self):
        res = self.run_cli("--role", "test_writer", stdin="not json")
        self.assertEqual(res.returncode, 2)
        self.assertIn("not valid JSON", res.stderr)
        res = self.run_cli("--role", "manifest", "--files-touched", "a.py",
                           stdin="{}")
        self.assertEqual(res.returncode, 2)

    def test_files_touched_flag_reaches_the_coder_check(self):
        res = self.run_cli("--role", "coder", "--files-touched",
                           "src/other.py", stdin=json.dumps(coder_out()))
        self.assertEqual(res.returncode, 1)
        self.assertIn("outside files_touched", res.stdout)


def example_keys(rel_path, heading):
    """Top-level keys of the first ```json example after ``heading``."""
    text = (ROOT / rel_path).read_text(encoding="utf-8")
    start = text.index(heading)
    block = re.search(r"```json\s*(.*?)```", text[start:], re.S)
    return frozenset(json.loads(block.group(1)))


class TestSpecKeysInSync(unittest.TestCase):
    """The validator's key sets must track the JSON examples in the specs."""

    def test_coder_prompt(self):
        self.assertEqual(
            example_keys("prompts/implement/coder.md", "## Output format"),
            vio.CODER_KEYS)

    def test_test_writer_prompt(self):
        self.assertEqual(
            example_keys("prompts/implement/test_writer.md",
                         "## Output format"),
            vio.TEST_WRITER_KEYS)

    def test_subagent_manifest(self):
        self.assertEqual(
            example_keys("agents/consilium-implement-subagent.md",
                         "## Output contract"),
            vio.MANIFEST_KEYS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
