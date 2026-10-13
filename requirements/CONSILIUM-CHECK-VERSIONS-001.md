---
milestone: v1.4.0
id: CONSILIUM-CHECK-VERSIONS-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: []
risk: 1
satisfies: [ARCH-CONSILIUM-REPO-GATES-001]
---

# check_versions

> Fails CI if `plugin.json` and `marketplace.json` semver drift apart, or if the vendored engine's MAP_ENGINE_VERSION (`scripts/reqmap_engine/__init__.py`) is not a valid dated engine version.

## Description

Every line in this section is binding.

- `check_versions.py` is the single point that asserts the plugin's semver stays aligned across `consilium/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, since Claude Code reads both as static data and neither manifest can import the other to stay in sync automatically; drift fails the build instead of shipping silently.
- `check_versions.py` mirrors `requirement-manager`'s `scripts/check_versions.py` (same mechanism, adopted 2026-07-06 after `marketplace.json` was found to have no `version` field at all while `plugin.json` had already drifted from an orphan `v1.4.0` git tag).
- `MAP_ENGINE_VERSION` (in `scripts/reqmap_engine/__init__.py`) is checked independently: it is a staleness-compare date stamp for the requirement-map engine, not a semver, and it is never compared against the plugin version.
- `plugin.json`'s `version` field is the canonical source; every `version` occurrence in `marketplace.json` (top-level and each `plugins[]` entry) equals it exactly, by string equality with no semver-range logic.
- A non-dict entry in `marketplace.json`'s `plugins[]` array is reported as a readable diagnostic (exit 1), never an unhandled `AttributeError`.
- `MAP_ENGINE_VERSION` matches `YYYY-MM-DD` optionally followed by `.N` (N a positive integer, same-day revision suffix); the regex anchor is line-start, so a docstring/comment mention preceding the real assignment cannot be matched instead.
- `--fix` rewrites only `marketplace.json` (never `plugin.json`, which stays the hand-edited canonical source), and is a no-op (exit 0, no write) when already aligned.
- `check_versions.py` reads `plugin.json`'s `version` field (the canonical semver source), `marketplace.json`'s top-level `version` and each `plugins[].version`, and `scripts/reqmap_engine/__init__.py`'s `MAP_ENGINE_VERSION` constant.
- `check_versions.py` prints `OK  semver aligned at '<version>' across N location(s); engine MAP_ENGINE_VERSION = '<date>'` to stdout on success.
- On drift, it prints `FAIL  version drift detected:` plus a per-location diff to stdout.
- `check_versions.py` exits 0 when aligned, and exits 1 on drift.
- `check_versions.py` exits 2 when a manifest or field is missing or unreadable.

## Verify intent

- None — resolved.

## Cases

- **CASE-1** — Given aligned manifests (plugin, marketplace, and engine all valid), when `check_versions.py` runs, then it exits 0 (tested in `scripts/test_check_versions.py`).
- **CASE-2** — Given a `marketplace.json` top-level or per-plugin-entry version mismatch, when `check_versions.py` runs, then it exits 1.
- **CASE-3** — Given a missing `plugin.json` `version` field, when `check_versions.py` runs, then it exits 2.
- **CASE-4** — Given a non-dict `plugins[]` entry, when `check_versions.py` runs, then it exits 1 without raising.
- **CASE-5** — Given a `MAP_ENGINE_VERSION` docstring mention before the real assignment, when `check_versions.py` runs, then that mention is ignored by the anchored regex.
- **CASE-6** — Given same-day revision suffixes (`.1`, `.2`, ...), when `check_versions.py` validates them, then they pass; `.0` and non-numeric suffixes do not.
- **CASE-7** — Given `--fix` run against a drifted `marketplace.json`, when it propagates `plugin.json`'s version into both `marketplace.json` locations, then a subsequent unflagged run passes.

## Context (non-binding)

**Current implementation** — `scripts/check_versions.py`, tested in `scripts/test_check_versions.py`.

<!-- verified-by: scripts/test_check_versions.py -->
