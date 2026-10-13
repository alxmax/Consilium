"""Tests for scripts/render_impl_preview.py (report + diff -> static HTML preview).

Run: python scripts/test_render_impl_preview.py   (exit 0 = all pass, 1 = a failure)

Coverage (Control tests_to_write, runs/2026-07-03_1443_html-preview-impl-step.json):
- round-trip: report + 2-file diff -> HTML contains success_criterion, chosen id
  and one section per file in the diff.
- escaping: hostile diff content (</script>, <img onerror=...>) never appears raw.
- spec-only: no --diff-file -> placeholder rendered, CLI exit 0.
- invalid report: missing required field -> exit 1; malformed JSON -> exit 2.
"""
# tested-by: CONSILIUM-RENDER-IMPL-PREVIEW-001
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent / "consilium"  # the shipped plugin (SKILL.md, modes/, prompts/, scripts/)
sys.path.insert(0, str(ROOT / "scripts"))
from render_impl_preview import render_preview_html, split_diff_sections  # noqa: E402

SCRIPT = ROOT / "scripts" / "render_impl_preview.py"

REPORT = {
    "success_criterion": "The frobnicator rejects empty input with ValueError.",
    "chosen_approach": "guard_clause_fix",
    "verification": "python scripts/test_frobnicator.py",
    "alternatives": [
        {"id": "do_nothing", "summary": "Keep current behavior.", "why_not": "goal unaddressed"}
    ],
    "voice_scores": {"generator": 0.8, "control": 0.7, "conservator": 0.1},
    "confidence": 0.74,
    "deliberation_log": [],
    "telemetry": {"mode": "sequential", "consilium_version": "v1.1-test"},
}

DIFF = """diff --git a/pkg/frob.py b/pkg/frob.py
--- a/pkg/frob.py
+++ b/pkg/frob.py
@@ -1,3 +1,5 @@
 def frob(x):
+    if not x:
+        raise ValueError("empty")
     return x * 2
diff --git a/pkg/util.py b/pkg/util.py
--- a/pkg/util.py
+++ b/pkg/util.py
@@ -1,2 +1,2 @@
-OLD = 1
+NEW = 2
"""

HOSTILE_DIFF = """diff --git a/evil.js b/evil.js
--- a/evil.js
+++ b/evil.js
@@ -1,1 +1,2 @@
+</script><script>alert(1)</script>
+<img onerror=alert(2) src=x>
"""


def _run_cli(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPT), *args],
        input=stdin, capture_output=True, text=True, encoding="utf-8",
    )


def run() -> int:
    passed = failed = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        ok = bool(cond)
        passed += ok
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  -> ' + detail}")

    # 1. Round-trip: spec + per-file diff sections all present.
    page = render_preview_html(REPORT, DIFF)
    check("round-trip: success_criterion rendered", REPORT["success_criterion"] in page)
    check("round-trip: chosen id rendered", "guard_clause_fix" in page)
    check("round-trip: file 1 section", "pkg/frob.py" in page)
    check("round-trip: file 2 section", "pkg/util.py" in page)
    check("round-trip: 2 diff sections split", len(split_diff_sections(DIFF)) == 2,
          repr([n for n, _ in split_diff_sections(DIFF)]))

    # 1b. Filename with spaces: git emits `diff --git a/a file.txt b/a file.txt`
    # unquoted; the section name must be the full `a file.txt`, not `file.txt`.
    spaced = split_diff_sections("diff --git a/a file.txt b/a file.txt\n@@ -1 +1 @@\n-x\n+y\n")
    check("spaced filename: section name keeps the space",
          bool(spaced) and spaced[0][0] == "a file.txt", repr([n for n, _ in spaced]))

    # 2. Escaping: hostile content never survives raw.
    hostile = render_preview_html(REPORT, HOSTILE_DIFF)
    check("escape: no raw </script> from diff", "</script><script>alert(1)" not in hostile)
    check("escape: no raw <img onerror>", "<img onerror=" not in hostile)
    check("escape: escaped form present", "&lt;/script&gt;" in hostile)

    # 2b. Theme toggle present (self-contained light/dark switch).
    check("theme toggle button present", 'id="theme-toggle"' in page)

    # 3. Spec-only: placeholder, no diff blocks.
    spec_only = render_preview_html(REPORT, None)
    check("spec-only: placeholder rendered", "No diff provided" in spec_only)
    check("spec-only: no diff section", '<div class="diff">' not in spec_only)

    with tempfile.TemporaryDirectory() as td:
        tdp = pathlib.Path(td)
        report_path = tdp / "report.json"
        report_path.write_text(json.dumps(REPORT), encoding="utf-8")
        out_path = tdp / "preview.html"

        # 4. CLI happy path: exit 0, file written, diff via stdin.
        proc = _run_cli(["--input", str(report_path), "--diff-file", "-",
                         "--output", str(out_path)], stdin=DIFF)
        check("cli: exit 0 on valid input", proc.returncode == 0, proc.stderr)
        check("cli: output file written", out_path.exists() and "pkg/frob.py" in out_path.read_text(encoding="utf-8"))

        # 4b. CLI diff via stdin with a leading UTF-8 BOM (PowerShell pipe):
        # the BOM must not defeat the first `diff --git` header.
        bom_out = tdp / "bom.html"
        proc = _run_cli(["--input", str(report_path), "--diff-file", "-",
                         "--output", str(bom_out)], stdin="﻿" + DIFF)
        bom_html = bom_out.read_text(encoding="utf-8") if bom_out.exists() else ""
        check("cli: BOM-prefixed stdin diff labels first file correctly",
              '<span class="fname">pkg/frob.py</span>' in bom_html
              and '<span class="fname">(diff)</span>' not in bom_html,
              proc.stderr)

        # 5. CLI spec-only: exit 0.
        proc = _run_cli(["--input", str(report_path), "--output", str(tdp / "spec_only.html")])
        check("cli: spec-only exit 0", proc.returncode == 0, proc.stderr)

        # 6. Missing required field -> exit 1, loud stderr.
        bad = dict(REPORT)
        bad.pop("chosen_approach")
        bad_path = tdp / "bad.json"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        proc = _run_cli(["--input", str(bad_path), "--output", str(tdp / "x.html")])
        check("cli: missing field exit 1", proc.returncode == 1, f"rc={proc.returncode}")
        check("cli: missing field named in stderr", "chosen_approach" in proc.stderr, proc.stderr)

        # 7. Malformed JSON -> exit 2.
        garbled = tdp / "garbled.json"
        garbled.write_text("{not json", encoding="utf-8")
        proc = _run_cli(["--input", str(garbled), "--output", str(tdp / "y.html")])
        check("cli: malformed JSON exit 2", proc.returncode == 2, f"rc={proc.returncode}")

        # 8. Unreadable report path -> exit 1.
        proc = _run_cli(["--input", str(tdp / "absent.json")])
        check("cli: absent report exit 1", proc.returncode == 1, f"rc={proc.returncode}")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
