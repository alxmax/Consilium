"""Manifest version-coherence gate (CI tooling — not part of the
deliberation engine).

The plugin's semver lives in two static manifests that no single
process can derive at load time (Claude Code reads plugin.json /
marketplace.json as data; neither can import the other). This script
is the single point that asserts they agree, so drift fails the build
instead of shipping silently. Mirrors requirement-manager's
scripts/check_versions.py (same mechanism, adopted 2026-07-06).

Two independent axes are checked:
  - semver  — canonical source is consilium/.claude-plugin/plugin.json
              `version`. Every occurrence in
              .claude-plugin/marketplace.json must equal it
              (top-level `version` + each `plugins[].version`).
  - engine  — MAP_ENGINE_VERSION in scripts/reqmap_engine/__init__.py
              is an ISO date with a different purpose (staleness
              compare); it is only sanity-checked for valid
              YYYY-MM-DD shape, with an optional `.N` (N>=1) same-day
              revision suffix, never compared against the semver.

Exit 0 = aligned. Exit 1 = drift (with a readable diff). Exit 2 = a
file/field is missing or unreadable. stdlib only.

Usage:
    python scripts/check_versions.py
    python scripts/check_versions.py --fix
    # propagate plugin.json's version into marketplace.json
"""
# implements: CONSILIUM-CHECK-VERSIONS-001
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = REPO_ROOT / "consilium" / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"
# engine >= 8.0.0 keeps MAP_ENGINE_VERSION in the package, not the reqmap.py CLI
ENGINE_VERSION_PY = REPO_ROOT / "scripts" / "reqmap_engine" / "__init__.py"

# line-anchored so a docstring/comment mention before the real
# assignment can't win
MAP_ENGINE_RE = re.compile(r'^MAP_ENGINE_VERSION\s*=\s*"([^"]+)"', re.M)


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"ERROR  cannot read {path.relative_to(REPO_ROOT)}: {e}")
        raise SystemExit(2)


def _fix(canonical: str) -> int:
    """Propagate the canonical plugin.json version into every
    marketplace.json occurrence, so a bump is one edit + one command
    instead of two hand-edits. Rewrites only when something changed;
    preserves 2-space indent + trailing NL."""
    market = _load_json(MARKETPLACE_JSON)
    before = json.dumps(market, sort_keys=True)
    market["version"] = canonical
    for plug in market.get("plugins", []):
        if isinstance(plug, dict):
            plug["version"] = canonical
    if json.dumps(market, sort_keys=True) == before:
        print(f"OK  marketplace.json already at {canonical!r} "
              f"— nothing to fix.")
        return 0
    MARKETPLACE_JSON.write_text(
        json.dumps(market, indent=2) + "\n", encoding="utf-8")
    print(f"fixed  marketplace.json synced to {canonical!r}.")
    return 0


def _marketplace_drift(canonical) -> tuple[list[str], int]:
    """Every semver occurrence in marketplace.json must equal the
    canonical source. Returns (errors, occurrence count)."""
    errors: list[str] = []
    market = _load_json(MARKETPLACE_JSON)
    occurrences = [("marketplace.version", market.get("version"))]
    for i, plug in enumerate(market.get("plugins", [])):
        if isinstance(plug, dict):
            occurrences.append(
                (f"marketplace.plugins[{i}].version", plug.get("version")))
        else:
            errors.append(
                f"  marketplace.plugins[{i}] is not an object: {plug!r}")
    for label, value in occurrences:
        if value != canonical:
            errors.append(
                f"  {label}: {value!r} != plugin.json version {canonical!r}")
    return errors, len(occurrences)


def _engine_version_errors(engine: str) -> list[str]:
    """YYYY-MM-DD with an optional `.N` same-day revision suffix
    (N a positive integer) — lets a second engine bump on the
    same calendar day get a distinct, still
    lexicographically-ordered version."""
    base, sep, rev = engine.partition(".")
    valid = True
    try:
        dt.date.fromisoformat(base)
    except ValueError:
        valid = False
    if sep and not (rev.isdigit() and int(rev) >= 1):
        valid = False
    if valid:
        return []
    return [
        f"  reqmap_engine/__init__.py: MAP_ENGINE_VERSION "
        f"{engine!r} is not a valid YYYY-MM-DD date "
        f"with an optional .N (N>=1) same-day revision"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Assert (or --fix) version coherence across the "
                    "manifests.")
    ap.add_argument("--fix", action="store_true",
                    help="rewrite marketplace.json to match "
                         "plugin.json's version, then verify")
    a = ap.parse_args(argv)

    errors: list[str] = []

    plugin = _load_json(PLUGIN_JSON)
    canonical = plugin.get("version")
    if not canonical:
        print(f"ERROR  no `version` in {PLUGIN_JSON.relative_to(REPO_ROOT)}")
        return 2

    if a.fix:
        rc = _fix(canonical)
        if rc:
            return rc

    errors, n_occurrences = _marketplace_drift(canonical)

    # Engine version is a separate axis — only validate it is a real
    # ISO date.
    try:
        text = ENGINE_VERSION_PY.read_text(encoding="utf-8")
    except OSError as e:
        print(f"ERROR  cannot read "
              f"{ENGINE_VERSION_PY.relative_to(REPO_ROOT)}: {e}")
        return 2
    m = MAP_ENGINE_RE.search(text)
    if not m:
        errors.append(
            "  reqmap_engine/__init__.py: MAP_ENGINE_VERSION not found")
        engine = None
    else:
        engine = m.group(1)
        errors += _engine_version_errors(engine)

    if errors:
        print("FAIL  version drift detected:")
        print("\n".join(errors))
        print(f"\ncanonical semver (plugin.json) = {canonical!r}")
        return 1

    print(f"OK  semver aligned at {canonical!r} across "
          f"{1 + n_occurrences} location(s); "
          f"engine MAP_ENGINE_VERSION = {engine!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
