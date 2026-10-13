"""Tests for the shipped plugin folder (consilium/).

An install — the Claude plugin directory or `apm install alxmax/Consilium/consilium`
— receives only this folder, and the directory scans every file in it. These
tests pin what may ship: the manifest, SKILL.md, README, LICENSE, the agents,
prompts, modes and runtime docs, and the runtime scripts. Tests, gates, hooks,
git automation, CDN-loading pages and oversize files stay outside.

Run:
    python scripts/test_plugin_folder.py
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402

PLUGIN = plugin_paths.PLUGIN_DIR
ALLOWED_FILES = {".claude-plugin/plugin.json", ".claude-plugin/icon.png",
                 "SKILL.md", "README.md", "LICENSE"}
IMAGES = (".png",)  # binary: size-checked, not text-scanned
ALLOWED_DIRS = {"agents", "prompts", "modes", "scripts", "docs"}
MAX_BYTES = 256 * 1024  # directory: larger non-image files are held for review


def shipped_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", "."], cwd=PLUGIN, capture_output=True,
        text=True, encoding="utf-8", check=True).stdout
    return [f for f in out.splitlines() if f.strip()]


class TestPluginFolder(unittest.TestCase):
    def setUp(self):
        self.files = shipped_files()
        self.assertTrue(self.files, "no tracked files under consilium/")

    def test_only_allowed_paths(self):
        bad = [f for f in self.files
               if f not in ALLOWED_FILES and f.split("/", 1)[0] not in ALLOWED_DIRS]
        self.assertEqual(bad, [])

    def test_no_tests_or_dev_tools_in_scripts(self):
        bad = [f for f in self.files if f.startswith("scripts/")
               and (not f.endswith(".py") or Path(f).name.startswith("test_"))]
        self.assertEqual(bad, [])

    def test_no_file_over_256_kib(self):
        big = [f for f in self.files if (PLUGIN / f).stat().st_size > MAX_BYTES]
        self.assertEqual(big, [])

    def test_no_git_automation_or_remote_scripts(self):
        hits = []
        for f in self.files:
            if f.endswith(IMAGES):
                continue
            text = (PLUGIN / f).read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\bgit\s+(push|commit)\b", text):
                hits.append(f"{f}: git push/commit")
            if re.search(r"<script[^>]+src=[\"']https?://", text):
                hits.append(f"{f}: remote <script src>")
        self.assertEqual(hits, [])

    def test_no_hidden_format_characters(self):
        # Invisible format characters (BOM, zero-width, bidi) are flagged by
        # install-time scanners; write them as escapes, e.g. "﻿".
        import unicodedata
        hits = []
        for f in self.files:
            if f.endswith(IMAGES):
                continue
            text = (PLUGIN / f).read_text(encoding="utf-8", errors="ignore")
            hits += [f"{f}: U+{ord(c):04X}" for c in set(text)
                     if unicodedata.category(c) == "Cf"]
        self.assertEqual(hits, [])

    def test_manifest_and_skill_present(self):
        for f in (".claude-plugin/plugin.json", ".claude-plugin/icon.png",
                  "SKILL.md", "README.md", "LICENSE"):
            self.assertIn(f, self.files)


if __name__ == "__main__":
    unittest.main(verbosity=2)
