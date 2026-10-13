"""Plan + gate-verify the post-deliberation implementation pipeline.

Companion to ``infer_pipeline.py``. Where that script infers *which* steps
apply, this one turns a completed Consilium report into an implementation
*dispatch plan* (Coder -> Test Writer || Reviewer) and provides the
red->green test gate verifier.

Like ``infer_pipeline.py``, this is a **planner**, not a dispatcher: the
orchestrating agent (``agents/consilium-implement-subagent.md``) performs
the actual sub-agent dispatch. This script only (a) extracts the spec +
role->prompt mapping, and (b) empirically verifies the red->green gate
when asked.

> Status: default for regression-risk changes (promoted 2026-05-25).
> Routing via recommend_implement_mode() in infer_pipeline.py. See
> SKILL.md Step 7.

Usage:
    python scripts/implement_pipeline.py --input runs/<file>.json --dry-run
    python scripts/implement_pipeline.py --input runs/<file>.json
    # prints plan JSON
    python scripts/implement_pipeline.py --verify-gate \\
        --test-cmd "pytest -x" --target solution.py
    python scripts/implement_pipeline.py --verify-gate \\
        --test-cmd "pytest -x" --target a.py b.py c.py

Flags:
    --dry-run      Print the dispatch plan and exit 0 (no side effects).
    --verify-gate  Run the red->green gate instead of planning (needs
                   --test-cmd + --target).
    --test-cmd     Test command for the gate (e.g. "pytest -x").
    --target       Implementation file(s) the gate stubs to produce the
                   RED run. Pass every Coder-written impl file (fan-out)
                   — stubbing one of N leaves the rest live.
    --stub-marker  Body injected to stub the target (default: "raise
                   NotImplementedError").

Exit codes:
    0   Plan printed / dry-run complete / gate passed.
    1   chosen_approach is do_nothing/skipped (no pipeline), or gate failed.
    2   Input invalid (JSON parse error, missing fields, or bad gate args).
"""
# implements: CONSILIUM-IMPLEMENT-PIPELINE-001

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shlex
import subprocess
import sys

from utils import force_utf8_streams

_SKILL_ROOT = pathlib.Path(__file__).parent.parent

# Role -> prompt template. Reviewer reuses the existing Control voice (no
# reviewer.md).
_ROLE_PROMPTS = {
    "coder": "prompts/implement/coder.md",
    "test_writer": "prompts/implement/test_writer.md",
    "reviewer": "prompts/voices/control.md",
}


def _resolve_chosen_candidate(report: dict, chosen: str) -> dict | None:
    """Full candidate object for `chosen` from the generator step, else None.

    coder.md's input contract promises `chosen_approach: {id, summary,
    sketch, rationale}`, but the report's top-level field is a bare id
    (docs/runs-schema.md) — resolve it so the Coder receives the sketch
    instead of an id-only spec its own thin-sketch rule would mark blocked.
    """
    for entry in report.get("deliberation_log") or []:
        if isinstance(entry, dict) and entry.get("step") == "generator":
            for cand in entry.get("candidates") or []:
                if isinstance(cand, dict) and cand.get("id") == chosen:
                    return cand
    return None


def build_plan(report: dict) -> dict:
    """Return the implementation dispatch plan from a deliberation report.

    Raises ValueError if chosen_approach is do_nothing/skipped (no pipeline).
    """
    chosen = report.get("chosen_approach")
    if chosen in ("do_nothing", "skipped", None, ""):
        raise ValueError(
            f"chosen_approach={chosen!r} — no implementation pipeline to run"
        )

    resolved = _resolve_chosen_candidate(report, chosen)
    spec = {
        "chosen_approach": resolved if resolved is not None else chosen,
        "chosen_resolved": resolved is not None,
        "success_criterion": report.get("success_criterion", ""),
        "verification": report.get("verification", ""),
    }
    roles = [
        {
            "role": role,
            "prompt_path": path,
            "exists": (_SKILL_ROOT / path).is_file(),
        }
        for role, path in _ROLE_PROMPTS.items()
    ]
    return {
        "spec": spec,
        "sequence": "coder -> (test_writer || reviewer)",
        "roles": roles,
        "rules": {
            "disjoint_paths": "coder writes impl; test_writer writes "
                              "test_*; reviewer read-only",
            "malformed_json": "hard-fail; retry once then abort",
            "gate": "tests must be RED on stub, GREEN on real impl",
        },
    }


def _run(test_cmd: str) -> int:
    """Run a test command, return its exit code (non-zero = failing/RED)."""
    return subprocess.run(
        shlex.split(test_cmd), cwd=str(pathlib.Path.cwd())
    ).returncode


def _run_stubbed(
    test_cmd: str,
    originals: dict[pathlib.Path, str],
    stub_marker: str,
) -> tuple[bool, list[str]]:
    """RED run: stub every target's def/async-def bodies, suite should
    now fail (exit != 0). Always restores every original.

    Returns ``(red_ok, restore_errors)``.
    """
    red_ok = False
    restore_errors: list[str] = []
    try:
        for t, original in originals.items():
            t.write_text(
                _stub_bodies(original, stub_marker), encoding="utf-8"
            )
        red_code = _run(test_cmd)
        red_ok = red_code != 0
    finally:
        # Best-effort restore: one failing write must not leave the
        # remaining siblings stubbed (the multi-target blast radius the
        # single-target gate did not have).
        for t, original in originals.items():
            try:
                t.write_text(original, encoding="utf-8")
            except OSError as exc:
                restore_errors.append(f"{t}: {exc}")
    return red_ok, restore_errors


def verify_red_green(
    test_cmd: str,
    target_files: list[str] | str,
    stub_marker: str = "raise NotImplementedError",
) -> dict:
    """Run the suite against the real impl (expect GREEN) and a
    fully-stubbed copy (expect RED).

    Accepts one target or many. When the Coder fan-out writes N
    implementation files, ALL of them must be stubbed together: stubbing
    a single file leaves the other N-1 live, so the suite can stay GREEN
    under the stub (it is still pinned by an un-stubbed file) and the
    gate spuriously fails a correctly-tested change. Stubbing every
    target at once makes the RED run break behavior across the whole
    passed set, so ``red_ok`` reflects all targets rather than one
    arbitrary file.

    ``red_ok`` is an EXISTENTIAL signal: it goes red when the suite
    fails on ANY stubbed target. So the gate verifies the tests are
    non-vacuously coupled to the passed implementation; it does NOT
    certify each file is individually covered (a passed file with zero
    tests still leaves the gate green if a sibling breaks the suite),
    and it cannot check files the caller did not pass — the
    orchestrator owns passing the full ``files_written`` union (see
    agents/consilium-implement-subagent.md).

    Never mutates the real targets permanently: each original text is
    held in memory and rewritten in the finally block — every captured
    file is restored even if a write or the stubbed run raises
    mid-loop, and one failing restore does not abort the rest (a
    partial restore would leave a sibling stubbed). A green run on the
    stubs means the tests do not pin behavior -> gate fails.
    """
    if isinstance(target_files, str):
        target_files = [target_files]

    targets = [pathlib.Path(t) for t in target_files]
    if not targets:
        return {"error": "no target files supplied", "gate_passed": False}
    missing = [str(t) for t in targets if not t.is_file()]
    if missing:
        return {
            "error": f"target(s) not found: {', '.join(missing)}",
            "gate_passed": False,
        }

    # Capture every original BEFORE any write so the finally block can
    # always restore all.
    originals = {t: t.read_text(encoding="utf-8") for t in targets}

    # GREEN run: real implementation should pass (exit 0).
    green_code = _run(test_cmd)
    green_ok = green_code == 0

    red_ok, restore_errors = _run_stubbed(test_cmd, originals, stub_marker)

    result: dict[str, object] = {
        "red_ok": red_ok,
        "green_ok": green_ok,
        "gate_passed": red_ok and green_ok,
    }
    if restore_errors:
        # A target left in stub state is a worse outcome than a gate
        # verdict — surface it and fail the gate so the caller does not
        # trust a half-restored tree.
        result["restore_errors"] = restore_errors
        result["gate_passed"] = False
    return result


def _header_colon_index(line: str) -> int:
    """Index of a def header's terminating colon on this physical line.

    Returns the position of the first ``:`` at bracket-depth 0 that is
    not inside a string or comment, or -1 if the header is not closed on
    this line. This is what tells a one-line compound def (``def f():
    return 1`` — colon present) apart from a genuine multi-line header
    opener (``def f(`` — no depth-0 colon yet). Bracket/string tracking
    keeps colons inside annotations, default dict literals, and string
    defaults (``def f(x: int, y={1: 2}, z="a:b"):``) from being mistaken
    for the header terminator.
    """
    depth = 0
    quote: str | None = None
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if quote is not None:
            i, quote = _step_in_string(line, i, quote)
            continue
        if c == "#":
            break  # comment: no header colon on this line beyond here
        if c == ":" and depth == 0:
            return i
        if c in "\"'":
            quote = c
        depth += (c in "([{") - (c in ")]}")
        i += 1
    return -1


def _step_in_string(line: str, i: int, quote: str) -> tuple[int, str | None]:
    """Advance one step inside a string literal opened by ``quote``.

    Returns the next index and the still-open quote (None once closed);
    a backslash skips the escaped character.
    """
    c = line[i]
    if c == "\\":
        return i + 2, quote
    return i + 1, (None if c == quote else quote)


def _strip_trailing_comment(line: str) -> str:
    """Return the line with any ``#`` comment removed (string-literal aware).

    Used by the multi-line-header scan in :func:`_stub_bodies`: a closing line
    like ``):  # noqa`` must still be recognized as terminating the header, so
    the comment is cut before the ``endswith(":")`` check.
    """
    quote: str | None = None
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if quote is not None:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#":
            return line[:i]
        i += 1
    return line


def _stub_bodies(source: str, stub_marker: str) -> str:
    """Replace each function body's first statement region with the
    stub marker.

    Heuristic + stdlib-only: after every `def ...:` / `async def ...:`
    header, insert the stub at the header's indent+4. This forces the
    suite RED without a full AST rewrite (sufficient for the gate's
    falsification purpose).

    Three header shapes are handled:
    - single-line header (``def f():`` with body on following lines) —
      stub is inserted as the first body line;
    - multi-line header (``def f(`` … ``):``) — lines accumulate until
      one ends with ``:``, then the stub is inserted at the opener's
      indent+4;
    - one-line compound def (``def f(): return 1``) — the inline body
      is dropped and replaced by the stub, so the function actually
      raises. (Previously this was misread as a multi-line opener: it
      set in_header and stole the *next* def's closing colon, leaving
      its own body live and silently defeating the RED gate.)

    Known heuristic limits (acceptable for the gate — it stubs normal
    impl files): a multi-line header whose closing line *also* carries
    an inline body (``)\n: return 1``), a `def`-like token inside a
    string literal, and a multi-line header whose *intermediate* line
    ends with a bare ``:`` outside brackets (closes the scan early).
    All are inherent to a line-scanner; use AST if these ever bite. (A
    trailing comment on the closing line — ``):  # noqa`` — is handled
    via _strip_trailing_comment.)
    """
    out: list[str] = []
    opener_re = re.compile(r"^(\s*)(async\s+def|def)\s+\w+")
    in_header = False
    header_indent: str = ""
    for line in source.splitlines():
        out.append(line)
        if in_header:
            # Keep accumulating until we see a line ending with ':'
            # (after cutting any trailing comment — `):  # noqa` closes
            # the header too)
            if _strip_trailing_comment(line).rstrip().endswith(":"):
                in_header = False
                out.append(f"{header_indent}{stub_marker}")
            continue
        m = opener_re.match(line)
        if not m:
            continue
        indent = m.group(1) + "    "
        colon = _header_colon_index(line)
        if colon == -1:
            # Header is not closed on this line → genuine multi-line opener.
            in_header = True
            header_indent = indent
            continue
        rest = line[colon + 1:].lstrip()
        if rest and not rest.startswith("#"):
            # One-line compound def: drop the inline body, keep the header.
            out[-1] = line[: colon + 1]
        out.append(f"{indent}{stub_marker}")
    return "\n".join(out) + ("\n" if source.endswith("\n") else "")


def main() -> None:
    force_utf8_streams()

    parser = argparse.ArgumentParser(
        description=(
            "Plan + gate-verify the post-deliberation implementation "
            "pipeline."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", help="Path to deliberation JSON (default: stdin)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the dispatch plan and exit (no side "
                             "effects)")
    parser.add_argument("--verify-gate", action="store_true",
                        help="Run the red->green gate instead of planning")
    parser.add_argument(
        "--test-cmd", help="Test command for the gate (e.g. 'pytest -x')"
    )
    parser.add_argument("--target", nargs="+",
                        help="Implementation file(s) the gate stubs for "
                             "the RED run (fan-out: pass every "
                             "Coder-written impl file, not just one)")
    parser.add_argument("--stub-marker", default="raise NotImplementedError",
                        help="Body injected to stub the target (default: "
                             "raise NotImplementedError)")
    args = parser.parse_args()

    if args.verify_gate:
        if not args.test_cmd or not args.target:
            print(
                "implement_pipeline: --verify-gate needs --test-cmd "
                "and --target",
                file=sys.stderr,
            )
            sys.exit(2)
        result = verify_red_green(args.test_cmd, args.target, args.stub_marker)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result.get("gate_passed") else 1)

    try:
        if args.input:
            with open(args.input, encoding="utf-8") as f:
                report = json.load(f)
        else:
            raw = sys.stdin.read()
            if not raw.strip():
                print(
                    "implement_pipeline: no input — pipe a deliberation "
                    "JSON or use --input",
                    file=sys.stderr,
                )
                sys.exit(2)
            report = json.loads(raw)
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        print(f"implement_pipeline: input error: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        plan = build_plan(report)
    except ValueError as exc:
        print(f"implement_pipeline: {exc}")
        sys.exit(1)

    print(f"\nImplementation pipeline: {plan['sequence']}")
    _chosen = plan['spec']['chosen_approach']
    print(
        f"  chosen : "
        f"{_chosen.get('id') if isinstance(_chosen, dict) else _chosen}"
    )
    for role in plan["roles"]:
        flag = "" if role["exists"] else "  [MISSING]"
        print(f"  {role['role']:<12} <- {role['prompt_path']}{flag}")
    if args.dry_run:
        print("(dry-run — no dispatch)")
    print(json.dumps({"plan": plan}, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
