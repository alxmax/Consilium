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
                   RED run (in a temporary copy of the working directory;
                   the originals are never written). Pass every
                   Coder-written impl file (fan-out) — stubbing one of N
                   leaves the rest live.
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
import shutil
import subprocess
import sys
import tempfile

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


def _run(
    test_cmd: str, cwd: pathlib.Path | str | None = None
) -> tuple[int, str]:
    """Run a test command; return ``(exit code, combined output)``.

    Output is captured so the gate can tell a behavioral failure from a
    technical one, and echoed to stderr so it stays visible (stdout is the
    gate's JSON verdict). Raises ``OSError`` when the command cannot start.
    """
    proc = subprocess.run(
        shlex.split(test_cmd),
        cwd=str(cwd or pathlib.Path.cwd()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sys.stderr.write(proc.stdout)
    return proc.returncode, proc.stdout


# Never copied into the disposable RED tree: VCS history and caches add size
# and no behavior the suite under test could depend on.
_COPY_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".consilium",
    ".pytest_cache", ".mypy_cache",
)


def _stub_evidence(stub_marker: str) -> str | None:
    """Exception name the stub raises (``NotImplementedError``), or None.

    A RED run must show this name in the suite output: that is what tells a
    behavioral failure (the stub fired) from a technical one (collection
    error, missing tool). A non-raising marker has no such evidence, so the
    gate falls back to the exit code alone for it.
    """
    m = re.match(r"\s*raise\s+([A-Za-z_][\w.]*)", stub_marker)
    return m.group(1).rsplit(".", 1)[-1] if m else None


def _syntax_problem(rel: pathlib.Path, source: str) -> str | None:
    """Why ``source`` is not valid Python, or None (non-.py files: skipped)."""
    if rel.suffix != ".py":
        return None
    try:
        compile(source, str(rel), "exec")
    except SyntaxError as exc:
        return f"{type(exc).__name__}: {exc.msg} (line {exc.lineno})"
    return None


def _run_red_in_copy(
    test_cmd: str,
    root: pathlib.Path,
    stubbed: dict[pathlib.Path, str],
    stub_marker: str,
) -> tuple[bool, str]:
    """RED run in a disposable copy of ``root`` with every target stubbed.

    The originals are never written, so no failure of this process (an
    exception, SIGTERM, a hard kill) can leave a target stubbed. The copy is
    the working tree as it is now, so uncommitted and new files are in it.

    Returns ``(red_ok, red_reason)``: red only when the suite failed AND its
    output shows the stub firing.
    """
    with tempfile.TemporaryDirectory(
        prefix="consilium-red-", ignore_cleanup_errors=True
    ) as tmp:
        tree = pathlib.Path(tmp) / "tree"
        shutil.copytree(root, tree, ignore=_COPY_IGNORE)
        for rel, text in stubbed.items():
            (tree / rel).write_text(text, encoding="utf-8")
        code, output = _run(test_cmd, cwd=tree)
    if code == 0:
        return False, "suite_passed"
    evidence = _stub_evidence(stub_marker)
    if evidence and evidence not in output:
        return False, "no_stub_evidence"
    return True, "behavioral"


def verify_red_green(
    test_cmd: str,
    target_files: list[str] | str,
    stub_marker: str = "raise NotImplementedError",
) -> dict:
    """Run the suite against the real impl (expect GREEN) and a
    fully-stubbed copy (expect RED).

    Accepts one target or many, all under the current directory. When the
    Coder fan-out writes N implementation files, ALL of them must be stubbed
    together: stubbing a single file leaves the other N-1 live, so the suite
    can stay GREEN under the stub (it is still pinned by an un-stubbed file)
    and the gate spuriously fails a correctly-tested change. Stubbing every
    target at once makes the RED run break behavior across the whole passed
    set, so ``red_ok`` reflects all targets rather than one arbitrary file.

    ``red_ok`` is an EXISTENTIAL signal: it goes red when the suite
    fails on ANY stubbed target. So the gate verifies the tests are
    non-vacuously coupled to the passed implementation; it does NOT
    certify each file is individually covered (a passed file with zero
    tests still leaves the gate green if a sibling breaks the suite),
    and it cannot check files the caller did not pass — the
    orchestrator owns passing the full ``files_written`` union (see
    agents/consilium-implement-subagent.md).

    The RED run happens in a temporary copy of the working directory (see
    ``_run_red_in_copy``), so the real targets are never modified. A RED
    counts only when the stubs are valid Python and the suite output shows
    the stub firing; compile-only checks, collection errors and an
    unavailable test tool do not. A green run on the stubs means the tests
    do not pin behavior -> gate fails. A suite that reaches files outside
    the working directory by absolute path is not stubbed there and fails
    the gate safe (stays GREEN).
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

    root = pathlib.Path.cwd().resolve()
    rels: list[pathlib.Path] = []
    outside: list[str] = []
    for t in targets:
        try:
            rels.append(t.resolve().relative_to(root))
        except ValueError:
            outside.append(str(t))
    if outside:
        return {
            "error": (
                f"target(s) outside the working directory: "
                f"{', '.join(outside)}"
            ),
            "gate_passed": False,
        }

    stubbed: dict[pathlib.Path, str] = {}
    for rel in rels:
        text = _stub_bodies((root / rel).read_text(encoding="utf-8"), stub_marker)
        problem = _syntax_problem(rel, text)
        if problem:
            return {
                "error": (
                    f"stubbed {rel} has invalid syntax ({problem}); "
                    f"no RED run made"
                ),
                "gate_passed": False,
            }
        stubbed[rel] = text

    try:
        # GREEN run: real implementation should pass (exit 0).
        green_code, _ = _run(test_cmd)
        red_ok, red_reason = _run_red_in_copy(
            test_cmd, root, stubbed, stub_marker
        )
    except OSError as exc:
        return {
            "error": f"test command could not run: {exc}",
            "gate_passed": False,
        }

    green_ok = green_code == 0
    return {
        "red_ok": red_ok,
        "red_reason": red_reason,
        "green_ok": green_ok,
        "gate_passed": red_ok and green_ok,
    }


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


def _body_indent(
    lines: list[str], header_end: int, opener_indent: str
) -> str:
    """Indent of the first real body line after ``lines[header_end]``.

    The stub must sit at the body's own indent: the original body stays below
    it, and any other indent (a fixed +4 on a 2-space or tab file) is an
    IndentationError, i.e. an invalid mutant. Falls back to opener + 4 spaces
    when no deeper line follows.
    """
    for nxt in lines[header_end + 1:]:
        stripped = nxt.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lead = nxt[: len(nxt) - len(nxt.lstrip())]
        if len(lead) > len(opener_indent):
            return lead
        break
    return opener_indent + "    "


def _stub_bodies(source: str, stub_marker: str) -> str:
    """Replace each function body's first statement region with the
    stub marker.

    Heuristic + stdlib-only: after every `def ...:` / `async def ...:`
    header, insert the stub at the body's own indent. This forces the
    suite RED without a full AST rewrite (sufficient for the gate's
    falsification purpose).

    Three header shapes are handled:
    - single-line header (``def f():`` with body on following lines) —
      stub is inserted as the first body line;
    - multi-line header (``def f(`` … ``):``) — lines accumulate until
      one ends with ``:``, then the stub is inserted at the body's indent;
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
    lines = source.splitlines()
    in_header = False
    header_indent: str = ""
    for i, line in enumerate(lines):
        out.append(line)
        if in_header:
            # Keep accumulating until we see a line ending with ':'
            # (after cutting any trailing comment — `):  # noqa` closes
            # the header too)
            if _strip_trailing_comment(line).rstrip().endswith(":"):
                in_header = False
                indent = _body_indent(lines, i, header_indent)
                out.append(f"{indent}{stub_marker}")
            continue
        m = opener_re.match(line)
        if not m:
            continue
        opener_indent = m.group(1)
        colon = _header_colon_index(line)
        if colon == -1:
            # Header is not closed on this line → genuine multi-line opener.
            in_header = True
            header_indent = opener_indent
            continue
        rest = line[colon + 1:].lstrip()
        if rest and not rest.startswith("#"):
            # One-line compound def: drop the inline body, keep the header.
            out[-1] = line[: colon + 1]
            out.append(f"{opener_indent}    {stub_marker}")
        else:
            indent = _body_indent(lines, i, opener_indent)
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
