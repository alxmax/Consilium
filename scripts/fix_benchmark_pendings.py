"""Convert PEND entries from a benchmark session to PEND_HEADLESS (post-hoc blind benchmark wrapper).

This script is a benchmark-only tool. Do not use it for general outcome management.

Blind benchmark workflow:
    1. Run ``claude -p`` normally — Claude does not know it is being benchmarked.
    2. Note the run-path(s) printed at Step 6 end (e.g. ``runs/2026-05-18_foo.json``).
    3. Call this script with those exact paths to reclassify their PEND entries as
       PEND_HEADLESS, which is excluded from pend_pressure and stale_pendings.

Idempotent: already-converted rows are silently skipped.

CLI:
    python scripts/fix_benchmark_pendings.py --run-paths runs/2026-05-18_foo.json
    python scripts/fix_benchmark_pendings.py --run-paths runs/foo.json runs/bar.json --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-paths", nargs="+", required=True, metavar="PATH",
                    help="run JSON files produced by the benchmark session")
    ap.add_argument("--feedback", default=None, help="path to FEEDBACK.html (default: .consilium/FEEDBACK.html, resolved relative to the repo)")
    ap.add_argument("--dry-run", action="store_true", help="print actions, don't write")
    args = ap.parse_args(argv)

    mark = (Path(__file__).resolve().parent.parent / "consilium" / "scripts"
            / "mark_outcome.py")
    errors = 0
    for run_path in args.run_paths:
        cmd = [sys.executable, "-X", "utf8", str(mark),
               "--run-path", run_path, "--outcome", "PEND_HEADLESS", "--benchmark"]
        if args.feedback:
            cmd += ["--feedback", args.feedback]
        if args.dry_run:
            cmd.append("--dry-run")
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if r.stdout:
            print(r.stdout, end="")
        if r.returncode != 0:
            print(r.stderr.strip(), file=sys.stderr)
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
