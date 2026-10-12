"""Repo-level version provenance for Consilium (review-hardened design).

Git is the version system: each deliberation records which repo state produced
it, so any `.consilium/runs/*.json` is reproducible via `git checkout`. No
bespoke per-prompt registry — git already content-hashes, versions (tags), and
diffs.

Two distinct fields, because one string cannot serve both roles (Reviewer 1,
review 2026-05-31_200016):

- ``consilium_version()`` — HUMAN display stamp: ``git describe --tags --always
  --dirty`` (e.g. ``v1.0.0``, ``v1.0.0-3-gabc123``, ``abc123``,
  ``abc123-dirty``), or ``"unknown"`` when git is unavailable / not a repo.
  FAILS OPEN (the scope_gate / probe_change idiom). For display & provenance
  only.
- ``consilium_ref()`` — a MACHINE diff operand: the bare committed HEAD sha, or
  ``""`` when the tree is dirty / git is unavailable. A ``"<sha>-dirty"`` string
  is NOT a valid ``git diff`` operand, so drift checks read THIS, never the
  stamp.

Drift is computed only against a *resolvable* ref
(``prompts_changed_since``): it never raises and returns 0 when the
ref is empty / ``"unknown"`` / unreachable (Reviewer 6's guard), so a
Step-0 advisory can call it unconditionally.

CLI:
    python scripts/version.py            # print the display version stamp
    python scripts/version.py --ref      # print the bare committed ref
                                          ("" if dirty/unknown)
    python scripts/version.py --drift REF # show prompts/ + modes/
                                           changed since REF
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UNKNOWN = "unknown"


def _git(args: list[str]) -> str | None:
    """Run a git command from the repo root. Return stdout (stripped),
    or None on any failure (git absent, non-zero exit) — fail-open,
    never raises."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def consilium_version() -> str:
    """Human-readable provenance stamp; ``"unknown"`` if git unavailable."""
    out = _git(["describe", "--tags", "--always", "--dirty"])
    return out if out else UNKNOWN


def consilium_ref() -> str:
    """A committed HEAD sha usable as a ``git diff`` operand, or ``""``.

    Returns ``""`` when the tree has uncommitted tracked changes (the
    run's prompts may not match any commit → not reconstructable) or
    when git is unavailable. ``.consilium/`` is gitignored, so
    writing a run file does not dirty the tree.

    ``--untracked-files=no`` so a stray untracked file (a scratch note, an
    un-added new script) does NOT blank the ref — matching ``git describe
    --dirty`` semantics used by consilium_version(), which ignores
    untracked files. Only uncommitted *tracked* changes void the ref,
    per the contract above.
    """
    status = _git(["status", "--porcelain", "--untracked-files=no"])
    if status is None or status.strip():
        return ""
    return _git(["rev-parse", "HEAD"]) or ""


def ref_resolves(ref: str) -> bool:
    """True iff ``ref`` names a reachable commit. False for
    ""/"unknown"/dirty/garbage."""
    if not ref or ref == UNKNOWN:
        return False
    return _git(
        ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]
    ) is not None


def prompts_changed_since(ref: str) -> int:
    """Count of prompts/ + modes/ files changed between ``ref`` and HEAD.

    Returns 0 (no drift) when ``ref`` is empty / "unknown" /
    unresolvable — never raises and never shells a malformed diff
    (Reviewer 6's guard). Safe to call
    unconditionally from a Step-0 advisory.
    """
    if not ref_resolves(ref):
        return 0
    out = _git(["diff", "--name-only", ref, "HEAD", "--", "prompts/", "modes/"])
    if not out:
        return 0
    return len([line for line in out.splitlines() if line.strip()])


def _drift_report(ref: str) -> str:
    if not ref_resolves(ref):
        return f"ref {ref!r} does not resolve to a commit — no drift computed."
    out = _git(["diff", "--stat", ref, "HEAD", "--", "prompts/", "modes/"])
    return out or f"no prompt/mode changes since {ref}."


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Consilium repo version provenance."
    )
    ap.add_argument("--ref", action="store_true",
                    help="print the bare committed ref ('' if dirty/unknown)")
    ap.add_argument("--drift", metavar="REF",
                    help="show prompts/ + modes/ files changed since REF")
    args = ap.parse_args(argv)
    if args.drift is not None:
        print(_drift_report(args.drift))
    elif args.ref:
        print(consilium_ref())
    else:
        print(consilium_version())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# implements: CONSILIUM-VERSION-001
