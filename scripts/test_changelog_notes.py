"""Tests for changelog_notes.py — the release-notes reader the release job uses.

Run:
    python scripts/test_changelog_notes.py
"""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import changelog_notes  # noqa: E402
from changelog_notes import section  # noqa: E402

SAMPLE = """# Changelog

Intro mentioning [1.2.0] in prose, not a heading.

## [1.2.0] — 2026-10-13

### Fixed
- second

## [1.1.0] — 2026-10-12

### Added
- first

## [1.0.0] — 2026-10-01
"""


class TestSection(unittest.TestCase):
    def test_returns_only_that_versions_body(self):
        body = section(SAMPLE, "1.2.0")
        self.assertEqual(body, "### Fixed\n- second")

    def test_last_section_runs_to_end_of_file(self):
        self.assertEqual(section(SAMPLE, "1.1.0"), "### Added\n- first")

    def test_missing_version_is_none(self):
        self.assertIsNone(section(SAMPLE, "9.9.9"))

    def test_empty_section_is_none(self):
        self.assertIsNone(section(SAMPLE, "1.0.0"))

    def test_prefix_version_does_not_match(self):
        self.assertIsNone(section(SAMPLE, "1.2"))


class TestMain(unittest.TestCase):
    def _run(self, version):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, "CHANGELOG.md")
            path.write_text(SAMPLE, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = changelog_notes.main([version, "--changelog", str(path)])
        return rc, out.getvalue(), err.getvalue()

    def test_found_prints_body_exit_0(self):
        rc, out, _ = self._run("1.2.0")
        self.assertEqual(rc, 0)
        self.assertIn("- second", out)
        self.assertNotIn("- first", out)

    def test_missing_exit_1(self):
        rc, out, err = self._run("2.0.0")
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("2.0.0", err)

    def test_repo_changelog_has_the_current_version(self):
        import json
        plugin = Path(__file__).resolve().parent.parent / "consilium" / ".claude-plugin" / "plugin.json"
        version = json.loads(plugin.read_text(encoding="utf-8"))["version"]
        self.assertIsNotNone(section(changelog_notes.DEFAULT_CHANGELOG.read_text(encoding="utf-8"), version))


if __name__ == "__main__":
    unittest.main(verbosity=2)
