"""Tests for check_public_leak.py — the RED path of the public-leak guard.

A live CI run only exercises the pass path (the repo is clean), so a
PATTERNS/SKIP_SUFFIX regression would silently disable the guard. These
tests feed synthetic leaking text through the scan_text seam.
Fixture strings are built by concatenation so this (tracked) file does
not itself trip the guard.

Run:
    python scripts/test_public_leak.py
"""
# tested-by: CONSILIUM-CHECK-PUBLIC-LEAK-001
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

import check_public_leak
from check_public_leak import SKIP_SUFFIX, scan_text

PRIVATE_REPO = "alxmax/" + "Consilium-Dev"
PUBLIC_REPO = "alxmax/" + "Consilium"
LOCAL_PATH = "Desktop" + chr(92) + "Doc" + chr(92) + "Consilium"


class TestScanText(unittest.TestCase):
    def test_private_repo_ref_detected(self):
        hits = scan_text("x.md", "see " + PRIVATE_REPO + " for source")
        self.assertEqual(len(hits), 1)
        self.assertIn("private dev repo", hits[0])

    def test_public_repo_allowed(self):
        self.assertEqual(scan_text("x.md", "install from " + PUBLIC_REPO), [])

    def test_local_dev_path_detected(self):
        hits = scan_text("x.md", "C:" + chr(92) + "Users" + chr(92) + "A" + chr(92) + LOCAL_PATH)
        self.assertEqual(len(hits), 1)
        self.assertIn("local dev absolute path", hits[0])

    def test_line_number_reported(self):
        hits = scan_text("x.md", "clean line" + chr(10) + PRIVATE_REPO)
        self.assertIn("x.md:2:", hits[0])

    def test_clean_text_no_hits(self):
        self.assertEqual(scan_text("x.md", "nothing to see"), [])


class TestSkipSuffix(unittest.TestCase):
    def test_binary_suffixes_skipped_by_main(self):
        # main() skips these before scanning; pin the suffix set so an
        # accidental addition (e.g. .md) cannot silently blind the guard.
        self.assertIn(".png", SKIP_SUFFIX)
        for forbidden in (".md", ".py", ".html", ".json"):
            self.assertNotIn(forbidden, SKIP_SUFFIX)


class TestMain(unittest.TestCase):
    """End-to-end main() over a temp working tree (tracked_files stubbed)."""

    def _run(self, files):
        """Write {name: text} into a temp cwd, run main(); (rc, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as td:
            for name, text in files.items():
                Path(td, name).write_text(text, encoding="utf-8")
            os.chdir(td)
            try:
                stub = mock.patch.object(
                    check_public_leak, "tracked_files",
                    return_value=list(files))
                with stub, contextlib.redirect_stdout(out):
                    with contextlib.redirect_stderr(err):
                        rc = check_public_leak.main()
            finally:
                os.chdir(cwd)
        return rc, out.getvalue(), err.getvalue()

    def test_clean_tree_exits_zero(self):
        # verifies: CONSILIUM-CHECK-PUBLIC-LEAK-001#CASE-1
        rc, out, _ = self._run({"a.md": "nothing", "b.md": PUBLIC_REPO})
        self.assertEqual(rc, 0)
        self.assertIn("public-leak guard: clean", out)

    def test_private_repo_ref_exits_one_with_file_and_line(self):
        # verifies: CONSILIUM-CHECK-PUBLIC-LEAK-001#CASE-2
        rc, out, err = self._run(
            {"a.md": "ok" + chr(10) + "see " + PRIVATE_REPO})
        self.assertEqual(rc, 1)
        self.assertIn("a.md:2:", err)
        self.assertNotIn("clean", out)

    def test_local_dev_path_exits_one(self):
        # verifies: CONSILIUM-CHECK-PUBLIC-LEAK-001#CASE-3
        rc, _, err = self._run({"a.md": "C:" + chr(92) + "Users" + chr(92)
                                + LOCAL_PATH})
        self.assertEqual(rc, 1)
        self.assertIn("a.md:1:", err)
        self.assertIn("local dev absolute path", err)

    def test_binary_and_image_files_are_skipped(self):
        # verifies: CONSILIUM-CHECK-PUBLIC-LEAK-001#CASE-4
        leak = PRIVATE_REPO + " " + LOCAL_PATH
        rc, out, _ = self._run({"i.png": leak, "f.woff": leak})
        self.assertEqual(rc, 0)
        self.assertIn("clean", out)

    def test_guard_file_excludes_itself(self):
        # verifies: CONSILIUM-CHECK-PUBLIC-LEAK-001#CASE-5
        rc, _, _ = self._run({"check_public_leak.py": PRIVATE_REPO})
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
