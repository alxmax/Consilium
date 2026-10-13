"""Tests for utils.py pure utility functions.

Covers canonical_run_path (path normalization), is_headless (env detection),
issue_penalty (severity lookup), and validate_keys (required-field guard).

Run:
    python scripts/test_utils.py
    python -m pytest scripts/test_utils.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-UTILS-001
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from utils import canonical_run_path, is_headless, issue_penalty, validate_keys


class TestCanonicalRunPath(unittest.TestCase):
    def test_plain_filename(self):
        self.assertEqual(canonical_run_path("run1.json"), "runs/run1.json")

    def test_full_consilium_path(self):
        self.assertEqual(canonical_run_path(".consilium/runs/run1.json"), "runs/run1.json")

    def test_absolute_path(self):
        result = canonical_run_path("/home/user/.consilium/runs/run1.json")
        self.assertEqual(result, "runs/run1.json")

    def test_windows_backslash_path(self):
        result = canonical_run_path("C:\\Users\\user\\.consilium\\runs\\run1.json")
        self.assertEqual(result, "runs/run1.json")

    def test_multiple_dots_in_name(self):
        result = canonical_run_path(".consilium/runs/run.2026.01.15.json")
        self.assertEqual(result, "runs/run.2026.01.15.json")


class TestIsHeadless(unittest.TestCase):
    def setUp(self):
        self._orig = os.environ.get("CLAUDE_HEADLESS")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("CLAUDE_HEADLESS", None)
        else:
            os.environ["CLAUDE_HEADLESS"] = self._orig

    def test_not_set_returns_false(self):
        os.environ.pop("CLAUDE_HEADLESS", None)
        self.assertFalse(is_headless())

    def test_set_to_1_returns_true(self):
        os.environ["CLAUDE_HEADLESS"] = "1"
        self.assertTrue(is_headless())

    def test_set_to_true_not_truthy(self):
        os.environ["CLAUDE_HEADLESS"] = "true"
        self.assertFalse(is_headless())

    def test_set_to_0_returns_false(self):
        os.environ["CLAUDE_HEADLESS"] = "0"
        self.assertFalse(is_headless())


class TestIssuePenalty(unittest.TestCase):
    def test_low_severity(self):
        self.assertEqual(issue_penalty({"severity": "low"}), 0.05)

    def test_medium_severity(self):
        self.assertEqual(issue_penalty({"severity": "medium"}), 0.15)

    def test_high_severity(self):
        self.assertEqual(issue_penalty({"severity": "high"}), 0.30)

    def test_missing_severity_defaults_to_medium(self):
        self.assertEqual(issue_penalty({}), 0.15)

    def test_unrecognized_severity_defaults_to_medium(self):
        self.assertEqual(issue_penalty({"severity": "unknown"}), 0.15)

    def test_non_dict_defaults_to_medium(self):
        self.assertEqual(issue_penalty("string"), 0.15)
        self.assertEqual(issue_penalty(None), 0.15)


class TestValidateKeys(unittest.TestCase):
    def test_all_keys_present_passes(self):
        validate_keys({"a": 1, "b": 2}, ["a", "b"], "ctx")

    def test_missing_key_raises(self):
        with self.assertRaises((ValueError, SystemExit)):
            validate_keys({"a": 1}, ["a", "b"], "ctx")

    def test_error_message_includes_key_and_context(self):
        try:
            validate_keys({}, ["missing_key"], "my_context")
            self.fail("expected exception")
        except (ValueError, SystemExit) as e:
            err = str(e)
            self.assertTrue("missing_key" in err or "my_context" in err)

    def test_non_dict_raises(self):
        with self.assertRaises((ValueError, SystemExit)):
            validate_keys("not a dict", ["x"], "ctx")  # type: ignore[arg-type]

    def test_empty_required_passes_any_dict(self):
        validate_keys({"a": 1}, [], "ctx")
        validate_keys({}, [], "ctx")

    def test_extra_keys_ignored(self):
        validate_keys({"a": 1, "b": 2, "c": 3}, ["a"], "ctx")


class TestDataDir(unittest.TestCase):
    """DATA_DIR follows the project (cwd) or $CONSILIUM_DATA_DIR, never the
    install dir — an install is replaced on every plugin/APM update."""

    SCRIPTS = str(Path(__file__).resolve().parent.parent / "consilium" / "scripts")
    PROBE = ("import sys; sys.path.insert(0, sys.argv[1]); import utils, "
             "vote_degeneracy as v; print(utils.DATA_DIR); "
             "print(utils.RUNS_DIR); print(utils.FEEDBACK_PATH); "
             "print(v.DEFAULT_RUNS)")

    def _probe(self, cwd, data_dir=None):
        import subprocess
        env = {k: val for k, val in os.environ.items()
               if k != "CONSILIUM_DATA_DIR"}
        if data_dir is not None:
            env["CONSILIUM_DATA_DIR"] = data_dir
        out = subprocess.run(
            [sys.executable, "-c", self.PROBE, self.SCRIPTS], cwd=cwd,
            env=env, capture_output=True, text=True, encoding="utf-8",
            check=True).stdout
        return [Path(line) for line in out.splitlines()]

    def test_default_is_cwd_relative(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            data, runs, fb, vd = self._probe(td)
            expected = Path(td).resolve() / ".consilium"
            self.assertEqual(data.resolve(), expected)
            self.assertEqual(runs.resolve(), expected / "runs")
            self.assertEqual(fb.resolve(), expected / "FEEDBACK.html")
            self.assertEqual(vd.resolve(), expected / "runs")

    def test_env_override_wins(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td, \
                tempfile.TemporaryDirectory() as store:
            data, runs, fb, vd = self._probe(td, data_dir=store)
            self.assertEqual(data, Path(store).resolve())
            self.assertEqual(runs, Path(store).resolve() / "runs")
            self.assertEqual(fb, Path(store).resolve() / "FEEDBACK.html")
            self.assertEqual(vd, Path(store).resolve() / "runs")

    def test_empty_env_falls_back_to_cwd(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            data = self._probe(td, data_dir="  ")[0]
            self.assertEqual(data.resolve(),
                             Path(td).resolve() / ".consilium")


if __name__ == "__main__":
    unittest.main(verbosity=2)
