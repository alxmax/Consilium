"""Decide whether a change is small enough to bypass full deliberation.

Reads diff signals via probe_change.py, checks them against thresholds and a
sensitive-path blocklist, then returns a JSON decision the caller uses to
either skip Generator/Control/Conservator or proceed normally.

Defaults (override via --config PATH or scope_gate.json in cwd):
  max_files = 1
  max_lines = 15            # added + removed
  blocklist = [auth/, security/, migrations/, .github/workflows/,
               **/*secrets*, .env*, Dockerfile, *.tf, *.tfvars,
               package.json, requirements.txt, go.mod, Cargo.toml, pom.xml]

Escape hatch: env CONSILIUM_FORCE_FULL=1 always returns should_skip=false
(useful when you want full deliberation regardless of probe size).

Output (always to stdout, exit 0 on success):
  {
    "should_skip": bool,
    "consent_required": bool,
    "magnitude": "low" | "medium" | "high" | "critical",
    "mode_ceiling": "sequential" | "dialectic" | "trias",
    "reason": str,
    "signals": {
      "files_changed": int,
      "lines_changed": int,
      "blocklist_hits": [{"path": str, "pattern": str}, ...]
    },
    "config_used": {"max_files": int, "max_lines": int, "blocklist": [...]}
  }

consent_required is the PRE-DISPATCH irreversibility consent gate (Generator
runs first, so the consent check must fire before any voice). It is True when
the diff touches a sensitive/irreversible path (blocklist hit) and — crucially —
FAILS SAFE: a probe/config failure returns consent_required=true (uncertainty
must NOT silently bypass consent). This is independent of should_skip's
fail-OPEN, which only governs whether to deliberate. Text-based irreversible
markers (e.g. "DROP TABLE", "no way back") are the orchestrator's complementary
check in SKILL.md Step 1.6.

magnitude thresholds (used by Trias lazy routing — independent of should_skip):
  low      — files ≤ 1, lines ≤ 15, no blocklist hits
  medium   — files ≤ 5, lines ≤ 100, no blocklist hits
  high     — files > 5 or lines > 100, no blocklist hits
  critical — any blocklist hit (auth, security, migrations, CI workflows,
             secrets)

mode_ceiling — mechanical upper bound on mode cost derived from magnitude:
  low      → sequential  (single-context deliberation is sufficient)
  medium   → sequential  (single-context sufficient; Dialectic/Trias over-spec)
  high     → dialectic   (large but routine refactor; Trias over-spec
             without a critical signal)
  critical → trias       (security/sensitive path; full 3-personality
             deliberation warranted)
  Blocklist hits force magnitude=critical and therefore mode_ceiling=trias.
  This makes advisory prose in SKILL.md enforceable via script output.

Probe failure (no git, not a repo, bad ref) -> should_skip=false with the
underlying error in `reason`. The gate fails OPEN: when in doubt, deliberate.

--signals-stdin bypasses the git probe and reads pre-computed signals as JSON
from stdin: {"files_changed": int, "lines_added": int, "lines_removed": int,
"paths": [str, ...]}. Used for deterministic, git-independent testing of the
classify/decide/mode_ceiling logic (e.g. eval scenarios).

CLI:
    python scripts/scope_gate.py
    python scripts/scope_gate.py --ref main
    python scripts/scope_gate.py --range origin/main..HEAD
    python scripts/scope_gate.py --files src/foo.py
    python scripts/scope_gate.py --config my_gate.json
    echo '{"files_changed":1,"paths":[".github/workflows/ci.yml"]}' | \
        python scripts/scope_gate.py --signals-stdin
"""
# implements: CONSILIUM-SCOPE-GATE-001

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import json
import os
import sys
from pathlib import Path


DEFAULT_CONFIG: dict = {
    "max_files": 1,
    "max_lines": 15,
    "blocklist": [
        "auth/",
        "security/",
        "migrations/",
        ".github/workflows/",
        "**/*secrets*",
        ".env*",
        "Dockerfile",
        "*.tf",
        "*.tfvars",
        "package.json",
        "requirements.txt",
        "go.mod",
        "Cargo.toml",
        "pom.xml",
    ],
}


def _load_probe_module():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "probe_change", here / "probe_change.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load probe_change.py from sibling path")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _path_matches(path: str, pattern: str) -> bool:
    """Match a forward-slash path against one of the supported pattern forms.

    Supported:
      - "dir/"        directory prefix at any depth (auth/foo, src/auth/foo)
      - "**/glob"     glob applied to any path component (basename-style)
      - "glob"        fnmatch on full path AND on basename (Dockerfile, *.tf)

    Paths and patterns are normalized to forward slashes and lowercased for
    cross-platform correctness (e.g. 'Dockerfile' matches 'dockerfile' on
    case-insensitive filesystems, and Windows backslashes are handled).
    """
    path = path.replace("\\", "/").lower()
    pattern = pattern.replace("\\", "/").lower()
    if pattern.endswith("/"):
        return path.startswith(pattern) or f"/{pattern}" in f"/{path}"
    if pattern.startswith("**/"):
        tail = pattern[3:]
        return any(fnmatch.fnmatchcase(p, tail) for p in path.split("/"))
    base = path.rsplit("/", 1)[-1]
    return (fnmatch.fnmatchcase(path, pattern)
            or fnmatch.fnmatchcase(base, pattern))


_MODE_CEILING: dict[str, str] = {
    "low": "sequential",
    "medium": "sequential",
    "high": "dialectic",
    "critical": "trias",
}


def classify_magnitude(files: int, lines: int, has_blocklist_hits: bool) -> str:
    """Return low / medium / high / critical for lazy Trias routing.

    Magnitude is independent of should_skip — it answers "how complex is this
    change?" so the caller can decide whether Dialectic is sufficient or full
    Trias is warranted.
    """
    if has_blocklist_hits:
        return "critical"
    if files > 5 or lines > 100:
        return "high"
    if files > 1 or lines > 15:
        return "medium"
    return "low"


def find_blocklist_hits(paths: list[str], blocklist: list[str]) -> list[dict]:
    hits: list[dict] = []
    for p in paths:
        for pat in blocklist:
            if _path_matches(p, pat):
                hits.append({"path": p, "pattern": pat})
                break
    return hits


def load_config(path: str | None) -> dict:
    if path is None:
        candidate = Path.cwd() / "scope_gate.json"
        if not candidate.exists():
            return {
                k: (list(v) if isinstance(v, list) else v)
                for k, v in DEFAULT_CONFIG.items()
            }
        path = str(candidate)
    with open(path, "r", encoding="utf-8") as f:
        user = json.load(f)
    if not isinstance(user, dict):
        raise RuntimeError(f"config {path} must be a JSON object")
    cfg = {
        k: (list(v) if isinstance(v, list) else v)
        for k, v in DEFAULT_CONFIG.items()
    }
    for k, v in user.items():
        if k in DEFAULT_CONFIG:
            cfg[k] = v
    return cfg


def _gather_signals(probe_mod, ref, range_, files):
    git_args: list[str] = []
    if range_:
        git_args = [range_]
    elif ref:
        git_args = [f"{ref}..HEAD"]
    else:
        git_args = ["HEAD"]
    if files:
        git_args += ["--", *files]
    text = probe_mod._run_numstat(git_args)
    summary, paths = probe_mod.parse_numstat(text)
    return summary, paths


def decide(summary: dict, paths: list[str], cfg: dict) -> dict:
    if "error" in summary:
        # Fail SAFE on consent: an undeterminable change must not silently
        # bypass the pre-dispatch consent gate (should_skip still fails OPEN →
        # deliberate).
        return {
            "should_skip": False,
            "consent_required": True,
            "magnitude": "critical",
            "mode_ceiling": "trias",
            "reason": f"probe failed: {summary['error']}",
            "signals": {
                "files_changed": 0,
                "lines_changed": 0,
                "blocklist_hits": [],
            },
        }
    files = summary.get("files_changed", 0)
    lines = summary.get("lines_added", 0) + summary.get("lines_removed", 0)
    hits = find_blocklist_hits(paths, cfg["blocklist"])
    signals = {
        "files_changed": files,
        "lines_changed": lines,
        "blocklist_hits": hits,
    }
    magnitude = classify_magnitude(files, lines, bool(hits))

    if files == 0:
        return {
            "should_skip": False,
            "consent_required": False,
            "magnitude": "low",
            "mode_ceiling": "sequential",
            "reason": "no changes detected",
            "signals": signals,
        }
    if hits:
        joined = ", ".join(sorted({h["pattern"] for h in hits}))
        return {
            "should_skip": False,
            "consent_required": True,
            "magnitude": magnitude,
            "mode_ceiling": _MODE_CEILING[magnitude],
            "reason": f"sensitive path matched: {joined}",
            "signals": signals,
        }
    if files > cfg["max_files"]:
        return {
            "should_skip": False,
            "consent_required": False,
            "magnitude": magnitude,
            "mode_ceiling": _MODE_CEILING[magnitude],
            "reason": f"{files} files > max_files={cfg['max_files']}",
            "signals": signals,
        }
    if lines > cfg["max_lines"]:
        return {
            "should_skip": False,
            "consent_required": False,
            "magnitude": magnitude,
            "mode_ceiling": _MODE_CEILING[magnitude],
            "reason": f"{lines} lines > max_lines={cfg['max_lines']}",
            "signals": signals,
        }
    return {
        "should_skip": True,
        "consent_required": False,
        "magnitude": magnitude,
        "mode_ceiling": _MODE_CEILING[magnitude],
        "reason": f"{files} file(s), {lines} lines, no sensitive paths",
        "signals": signals,
    }


def _read_signals(args: argparse.Namespace) -> tuple[dict, list]:
    """Signals from stdin (--signals-stdin) or from probing git; an error
    is carried in the summary, never raised, so ``decide`` fails safe."""
    if args.signals_stdin:
        try:
            payload = json.load(sys.stdin)
            summary = {
                "files_changed": int(payload.get("files_changed", 0)),
                "lines_added": int(payload.get("lines_added", 0)),
                "lines_removed": int(payload.get("lines_removed", 0)),
            }
            paths = list(payload.get("paths", []))
        except (
            json.JSONDecodeError, ValueError, TypeError, AttributeError
        ) as exc:
            summary = {"error": f"bad --signals-stdin payload: {exc}"}
            paths = []
    else:
        try:
            probe_mod = _load_probe_module()
            summary, paths = _gather_signals(
                probe_mod, args.ref, args.range_, args.files
            )
        except RuntimeError as exc:
            summary = {"error": str(exc)}
            paths = []
    return summary, paths


def main(argv: list[str] | None = None) -> int:
    # Check env override first — before any config load attempt so a config
    # failure cannot shadow the escape hatch.
    force_full = os.environ.get("CONSILIUM_FORCE_FULL") == "1"

    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--ref", help="diff <ref>..HEAD")
    mode.add_argument("--range", dest="range_", help="diff <A>..<B>")
    ap.add_argument("--files", nargs="+", help="restrict to specific paths")
    ap.add_argument(
        "--config",
        help="path to scope_gate.json (default: ./scope_gate.json if exists)",
    )
    ap.add_argument(
        "--signals-stdin",
        action="store_true",
        help=(
            "read pre-computed signals as JSON from stdin instead of "
            "probing git"
        ),
    )
    args = ap.parse_args(argv)

    if force_full:
        json.dump(
            {
                "should_skip": False,
                "consent_required": False,
                "magnitude": "critical",
                "mode_ceiling": "trias",
                "reason": "CONSILIUM_FORCE_FULL=1 (override)",
                "signals": {
                    "files_changed": 0,
                    "lines_changed": 0,
                    "blocklist_hits": [],
                    "forced": True,
                },
                "config_used": DEFAULT_CONFIG,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    try:
        cfg = load_config(args.config)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        json.dump(
            {
                "should_skip": False,
                "consent_required": True,
                "magnitude": "high",
                "mode_ceiling": _MODE_CEILING["high"],
                "reason": f"config load failed: {exc}",
                "signals": {
                    "files_changed": 0,
                    "lines_changed": 0,
                    "blocklist_hits": [],
                },
                "config_used": DEFAULT_CONFIG,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    summary, paths = _read_signals(args)

    result = decide(summary, paths, cfg)
    result["config_used"] = cfg
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
