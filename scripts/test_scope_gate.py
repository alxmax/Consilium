"""Tests for scope_gate.py pure functions.

Covers _path_matches (glob/prefix detection), classify_magnitude (thresholds),
find_blocklist_hits (pattern scanning), load_config (JSON merging), and
decide (skip/magnitude/mode-ceiling logic).

Run:
    python scripts/test_scope_gate.py
    python -m pytest scripts/test_scope_gate.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-SCOPE-GATE-001
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from scope_gate import (
    DEFAULT_CONFIG,
    _path_matches,
    classify_magnitude,
    decide,
    find_blocklist_hits,
    load_config,
)


class TestPathMatches(unittest.TestCase):
    def test_directory_prefix(self):
        self.assertTrue(_path_matches("auth/foo.py", "auth/"))
        self.assertTrue(_path_matches("src/auth/foo.py", "auth/"))
        self.assertFalse(_path_matches("authn/foo.py", "auth/"))

    def test_double_star_glob(self):
        self.assertTrue(_path_matches("secrets.json", "**/*secrets*"))
        self.assertTrue(_path_matches("src/secrets.py", "**/*secrets*"))

    def test_extension_glob(self):
        self.assertTrue(_path_matches("main.py", "*.py"))
        self.assertTrue(_path_matches("src/main.py", "*.py"))
        self.assertFalse(_path_matches("main.js", "*.py"))

    def test_env_prefix(self):
        self.assertTrue(_path_matches(".env", ".env*"))
        self.assertTrue(_path_matches(".env.local", ".env*"))
        self.assertFalse(_path_matches("env", ".env*"))

    def test_case_insensitive(self):
        self.assertTrue(_path_matches("AUTH/foo.py", "auth/"))

    def test_backslash_normalization(self):
        self.assertTrue(_path_matches("auth\\foo.py", "auth/"))


class TestClassifyMagnitude(unittest.TestCase):
    def test_low(self):
        self.assertEqual(classify_magnitude(1, 10, False), "low")
        self.assertEqual(classify_magnitude(0, 0, False), "low")

    def test_medium(self):
        self.assertEqual(classify_magnitude(2, 15, False), "medium")
        self.assertEqual(classify_magnitude(1, 20, False), "medium")

    def test_high(self):
        self.assertEqual(classify_magnitude(6, 50, False), "high")
        self.assertEqual(classify_magnitude(1, 200, False), "high")

    def test_critical_when_blocklist_hit(self):
        self.assertEqual(classify_magnitude(1, 1, True), "critical")
        self.assertEqual(classify_magnitude(0, 0, True), "critical")

    def test_lines_boundary(self):
        self.assertEqual(classify_magnitude(1, 15, False), "low")
        self.assertEqual(classify_magnitude(1, 16, False), "medium")


class TestFindBlocklistHits(unittest.TestCase):
    def test_single_match(self):
        hits = find_blocklist_hits(["auth/login.py"], ["auth/", "security/"])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["path"], "auth/login.py")

    def test_no_match(self):
        self.assertEqual(find_blocklist_hits(["src/main.py"], ["auth/"]), [])

    def test_multiple_paths(self):
        paths = ["src/main.py", "auth/login.py", "security/check.py"]
        hits = find_blocklist_hits(paths, ["auth/", "security/"])
        self.assertEqual(len(hits), 2)

    def test_glob_pattern(self):
        hits = find_blocklist_hits(["src/secrets.json", "main.py"], ["**/*secrets*"])
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["path"], "src/secrets.json")

    def test_one_hit_per_path(self):
        hits = find_blocklist_hits(["auth/secrets.py"], ["auth/", "**/*secrets*"])
        self.assertEqual(len(hits), 1)


class TestLoadConfig(unittest.TestCase):
    def test_default_when_no_file(self):
        cfg = load_config(None)
        self.assertEqual(cfg["max_files"], DEFAULT_CONFIG["max_files"])
        self.assertEqual(cfg["max_lines"], DEFAULT_CONFIG["max_lines"])
        self.assertIn("auth/", cfg["blocklist"])

    def test_merge_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"max_files": 5}, f)
            fname = f.name
        try:
            cfg = load_config(fname)
            self.assertEqual(cfg["max_files"], 5)
            self.assertEqual(cfg["max_lines"], DEFAULT_CONFIG["max_lines"])
        finally:
            Path(fname).unlink()

    def test_custom_blocklist_replaces_default(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"blocklist": ["custom/"]}, f)
            fname = f.name
        try:
            cfg = load_config(fname)
            self.assertEqual(cfg["blocklist"], ["custom/"])
        finally:
            Path(fname).unlink()


class TestDecide(unittest.TestCase):
    def test_low_change_skips(self):
        result = decide({"files_changed": 1, "lines_added": 5, "lines_removed": 0}, ["main.py"], DEFAULT_CONFIG)
        self.assertTrue(result["should_skip"])
        self.assertEqual(result["magnitude"], "low")

    def test_medium_does_not_skip(self):
        result = decide({"files_changed": 2, "lines_added": 50, "lines_removed": 0}, ["a.py", "b.py"], DEFAULT_CONFIG)
        self.assertFalse(result["should_skip"])
        self.assertEqual(result["magnitude"], "medium")

    def test_blocklist_hit_is_critical(self):
        result = decide({"files_changed": 1, "lines_added": 5, "lines_removed": 0}, ["auth/login.py"], DEFAULT_CONFIG)
        self.assertFalse(result["should_skip"])
        self.assertEqual(result["magnitude"], "critical")
        self.assertEqual(result["mode_ceiling"], "trias")

    def test_probe_error_is_critical(self):
        result = decide({"error": "git not found"}, [], DEFAULT_CONFIG)
        self.assertEqual(result["magnitude"], "critical")
        self.assertFalse(result["should_skip"])

    def test_output_has_required_keys(self):
        result = decide({"files_changed": 1, "lines_added": 5, "lines_removed": 0}, ["main.py"], DEFAULT_CONFIG)
        for key in ("should_skip", "magnitude", "mode_ceiling", "reason", "signals"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
