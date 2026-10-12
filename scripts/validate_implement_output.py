"""Validate the STRICT-JSON output of the implement pipeline's sub-agents.

The Coder (``prompts/implement/coder.md``), the Test Writer
(``prompts/implement/test_writer.md``) and the implement-subagent's final
manifest (``agents/consilium-implement-subagent.md``) each promise a JSON
shape, but nothing checked it. This script does, deterministically and
without judging the code itself: it looks at structure, types and the
cross-field rules those specs state (blocked => reason, disjoint paths,
red->green reporting).

Usage:
    python scripts/validate_implement_output.py --role coder \\
        --input coder_out.json [--files-touched a.py b.py]
    python scripts/validate_implement_output.py --role test_writer < out.json
    python scripts/validate_implement_output.py --role manifest < out.json

Roles:
    coder        Coder output (files_written, scope_escapes, blocked...).
    test_writer  Test Writer output (test_files_written, tests...).
    manifest     implement-subagent final manifest (nested ``gate``).

Flags:
    --files-touched  Coder only: paths the Coder may write; a written path
                     outside this set is a problem.

Exit codes:
    0   Output is well-formed and consistent.
    1   One or more problems (printed to stdout, one per line).
    2   Not JSON, or bad arguments.
"""
# implements: CONSILIUM-IMPLEMENT-CODER-001
# implements: CONSILIUM-IMPLEMENT-TEST-WRITER-001

from __future__ import annotations

import argparse
import json
import pathlib
import posixpath
import sys

from utils import force_utf8_streams

# Top-level keys each spec's JSON example carries. test_validate_implement_
# output.py asserts these stay equal to the examples in the spec files.
CODER_KEYS = frozenset({
    "files_written", "maps_to_criterion", "scope_escapes", "blocked",
    "blocked_reason",
})
TEST_WRITER_KEYS = frozenset({"test_files_written", "tests", "uncoverable"})
MANIFEST_KEYS = frozenset({
    "spec", "files_written", "test_files_written", "gate", "gate_rejected",
    "review", "blocked", "blocked_reason",
})


def _norm(path: object) -> str:
    """Comparable form of a path: forward slashes, no ./, lower-case."""
    text = str(path).replace("\\", "/")
    return posixpath.normpath(text).lower()


def _is_test_path(path: object) -> bool:
    return posixpath.basename(_norm(path)).startswith("test_")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _missing(out: dict, keys: frozenset[str]) -> list[str]:
    absent = sorted(keys - out.keys())
    return [f"missing keys: {', '.join(absent)}"] if absent else []


def _entry_problems(items: object, name: str, fields: tuple[str, ...],
                    lists: tuple[str, ...] = ()) -> list[str]:
    """Each entry must be an object with non-empty text ``fields`` and
    list-of-text ``lists``."""
    if not isinstance(items, list):
        return [f"{name} must be a list"]
    problems = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append(f"{name}[{i}] must be an object")
            continue
        problems += [f"{name}[{i}].{f} must be non-empty text"
                     for f in fields if not _text(item.get(f))]
        problems += [f"{name}[{i}].{f} must be a list of text"
                     for f in lists
                     if not (isinstance(item.get(f), list)
                             and all(_text(x) for x in item[f]))]
    return problems


def _paths(items: object) -> list[str]:
    """Normalised ``path`` of every well-formed entry in ``items``."""
    if not isinstance(items, list):
        return []
    return [_norm(i["path"]) for i in items
            if isinstance(i, dict) and _text(i.get("path"))]


def _blocked_problems(out: dict) -> list[str]:
    """blocked must be a bool; blocked => reason, not blocked => null."""
    blocked = out.get("blocked")
    if not isinstance(blocked, bool):
        return ["blocked must be true or false"]
    if blocked and not _text(out.get("blocked_reason")):
        return ["blocked is true but blocked_reason is empty"]
    if not blocked and out.get("blocked_reason") is not None:
        return ["blocked is false but blocked_reason is set"]
    return []


def _reason_entries_problems(items: object, name: str) -> list[str]:
    """Entries carry a reason: text, or an object with a text ``reason``.
    The specs do not pin their shape, so both are accepted."""
    if not isinstance(items, list):
        return [f"{name} must be a list"]
    return [f"{name}[{i}] needs a non-empty reason"
            for i, item in enumerate(items)
            if not (_text(item) or (isinstance(item, dict)
                                    and _text(item.get("reason"))))]


def validate_coder(out: object,
                   files_touched: list[str] | None = None) -> list[str]:
    """Problems with a Coder output (empty list = valid)."""
    if not isinstance(out, dict):
        return ["output must be a JSON object"]
    problems = _missing(out, CODER_KEYS)
    if problems:
        return problems
    problems += _blocked_problems(out)
    files = out["files_written"]
    problems += _entry_problems(files, "files_written",
                                ("path", "purpose"), ("symbols",))
    scope = out["scope_escapes"]
    if not (isinstance(scope, list) and all(_text(s) for s in scope)):
        problems.append("scope_escapes must be a list of paths")
        scope = []
    if out["blocked"] is True:
        if files:
            problems.append("blocked but files_written is not empty")
    else:
        if isinstance(files, list) and not files:
            problems.append("files_written is empty and not blocked")
        if not _text(out["maps_to_criterion"]):
            problems.append("maps_to_criterion must be non-empty text")
    written = _paths(files)
    problems += [f"Coder wrote a test file: {p}" for p in written
                 if _is_test_path(p)]
    problems += [f"{p} is both written and in scope_escapes"
                 for p in written if p in {_norm(s) for s in scope}]
    if files_touched is not None:
        allowed = {_norm(p) for p in files_touched}
        problems += [f"{p} is outside files_touched" for p in written
                     if p not in allowed]
    return problems


def validate_test_writer(out: object) -> list[str]:
    """Problems with a Test Writer output (empty list = valid)."""
    if not isinstance(out, dict):
        return ["output must be a JSON object"]
    problems = _missing(out, TEST_WRITER_KEYS)
    if problems:
        return problems
    files = out["test_files_written"]
    problems += _entry_problems(files, "test_files_written",
                                ("path", "covers"))
    if isinstance(files, list):
        if not files:
            problems.append("test_files_written is empty")
        problems += [f"test_files_written[{i}].path must start with test_"
                     for i, f in enumerate(files)
                     if isinstance(f, dict) and _text(f.get("path"))
                     and not _is_test_path(f["path"])]
    tests = out["tests"]
    if not isinstance(tests, list):
        problems.append("tests must be a list")
    else:
        for i, t in enumerate(tests):
            if not isinstance(t, dict) or not _text(t.get("name")):
                problems.append(f"tests[{i}] needs a name")
            elif t.get("fails_on_empty_impl") is not True:
                problems.append(
                    f"tests[{i}] ({t['name']}) fails_on_empty_impl is not "
                    "true")
    problems += _reason_entries_problems(out["uncoverable"], "uncoverable")
    return problems


def validate_manifest(out: object) -> list[str]:
    """Problems with an implement-subagent manifest (empty = valid)."""
    if not isinstance(out, dict):
        return ["output must be a JSON object"]
    if "error" in out:  # the documented abort object, e.g.
        # {"error": "subagent_json_invalid", "role": "coder"}
        return [] if _text(out["error"]) else ["error must be non-empty text"]
    problems = _missing(out, MANIFEST_KEYS)
    if problems:
        return problems
    problems += _blocked_problems(out)
    if out["blocked"] is True:  # nothing was implemented; no gate to check
        return problems
    problems += _entry_problems(out["files_written"], "files_written",
                                ("path",), ("symbols",))
    files = out["test_files_written"]
    problems += _entry_problems(files, "test_files_written",
                                ("path", "covers"))
    if isinstance(files, list):
        problems += [f"test_files_written[{i}].path must start with test_"
                     for i, f in enumerate(files)
                     if isinstance(f, dict) and _text(f.get("path"))
                     and not _is_test_path(f["path"])]
    return problems + _gate_problems(out)


def _gate_problems(out: dict) -> list[str]:
    """gate is internally consistent and any failure is reported."""
    gate = out["gate"]
    fields = ("red_ok", "green_ok", "gate_passed")
    if not (isinstance(gate, dict)
            and all(isinstance(gate.get(f), bool) for f in fields)):
        return ["gate needs boolean red_ok, green_ok and gate_passed"]
    problems = _reason_entries_problems(out["gate_rejected"], "gate_rejected")
    rejected = out["gate_rejected"]
    if gate["gate_passed"] and not (gate["red_ok"] and gate["green_ok"]):
        problems.append("gate_passed is true but red_ok/green_ok is false")
    if not gate["gate_passed"] and not rejected:
        problems.append("gate failed but gate_rejected is empty")
    if not gate["red_ok"] and not rejected:
        problems.append("a test passed under the stub (red_ok false) but "
                        "gate_rejected is empty")
    return problems


_VALIDATORS = {
    "coder": validate_coder,
    "test_writer": validate_test_writer,
    "manifest": validate_manifest,
}


def main() -> None:
    force_utf8_streams()
    parser = argparse.ArgumentParser(
        description="Validate implement-pipeline sub-agent JSON output.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--role", required=True, choices=sorted(_VALIDATORS))
    parser.add_argument("--input", help="JSON file (default: stdin)")
    parser.add_argument("--files-touched", nargs="+", metavar="PATH",
                        help="Coder only: paths the Coder may write")
    args = parser.parse_args()
    if args.files_touched and args.role != "coder":
        parser.error("--files-touched applies to --role coder only")
    try:
        raw = (pathlib.Path(args.input).read_text(encoding="utf-8")
               if args.input else sys.stdin.read())
        out = json.loads(raw.lstrip("﻿"))
    except (OSError, ValueError) as exc:
        print(f"not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)
    if args.role == "coder":
        problems = validate_coder(out, args.files_touched)
    else:
        problems = _VALIDATORS[args.role](out)
    for problem in problems:
        print(problem)
    if not problems:
        print(f"OK: {args.role} output is well-formed")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
