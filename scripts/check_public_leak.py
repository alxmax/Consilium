"""Guard: the published repo must not point back to its private source.

Fails (exit 1) if any tracked file references the private development
repository (any `alxmax/[Cc]onsilium…` that is not `…_Demo`) or leaks a
local absolute dev path. This keeps the public release repo decoupled from
its private source across rebuilds and dev->demo migrations — a private-repo
reference becomes un-shippable rather than a silent leak (e.g. the explainer's
"View repository" link, which once pointed at the private repo).

    python scripts/check_public_leak.py
    # exit 1 + offending file:line on any hit

Stdlib only. Wired into CI (.github/workflows/ci.yml). Patterns are written
with character classes so this guard file does not match its own source.
"""
# implements: CONSILIUM-CHECK-PUBLIC-LEAK-001

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Owner-qualified repo refs only (the bare project name "consilium" appears in
# countless legitimate paths/strings). `_Demo` is the allowed public repo.
PATTERNS = [
    (
        re.compile(r"alxmax/[Cc]onsilium(?!_[Dd]emo)"),
        "reference to the private dev repo",
    ),
    (
        re.compile(r"Desktop[\\/]+Doc[\\/]+[Cc]onsilium"),
        "local dev absolute path",
    ),
]
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
               ".woff", ".woff2", ".ttf", ".zip", ".pdf")
SELF = Path(__file__).name


def tracked_files() -> list[str]:
    # encoding="utf-8" is load-bearing: without it text=True decodes via
    # locale.getpreferredencoding() (cp1252 on Windows), so a non-ASCII tracked
    # filename mis-decodes to a path that read_text() can't find — the file is
    # then silently dropped from the leak scan by main()'s `except OSError`.
    # Same fix already applied in probe_change._run_numstat (PR #332).
    out = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return [f for f in out.splitlines() if f.strip()]


def scan_text(label: str, text: str) -> list[str]:
    """All PATTERNS hits in `text`, formatted as report lines (testable seam).

    Extracted so the RED path is exercisable by scripts/test_public_leak.py —
    a live CI run only ever sees a clean repo, so a PATTERNS regression could
    otherwise disable the guard with no signal (audit 2026-07-02).
    """
    hits: list[str] = []
    for pat, desc in PATTERNS:
        for m in pat.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"  {label}:{line}: {desc}: {m.group(0)!r}")
    return hits


def main() -> int:
    hits: list[str] = []
    for f in tracked_files():
        if f.endswith(SELF) or f.lower().endswith(SKIP_SUFFIX):
            continue
        try:
            text = Path(f).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        hits.extend(scan_text(f, text))

    if hits:
        print(
            "public-leak guard FAILED — the published repo must not "
            "point back to "
            "the private dev repo or leak local paths:",
            file=sys.stderr,
        )
        print("\n".join(hits), file=sys.stderr)
        return 1
    print("public-leak guard: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
