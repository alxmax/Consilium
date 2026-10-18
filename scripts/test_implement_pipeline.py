"""Tests for _stub_bodies() in implement_pipeline.py.

Run:
    python scripts/test_implement_pipeline.py
"""
# tested-by: CONSILIUM-IMPLEMENT-PIPELINE-001
# tested-by: CONSILIUM-IMPLEMENT-CODER-001
# tested-by: CONSILIUM-IMPLEMENT-TEST-WRITER-001
import json
import os
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

import implement_pipeline as _ip
from implement_pipeline import _stub_bodies, build_plan, verify_red_green

MARKER = "raise NotImplementedError"
_PY = shlex.quote(sys.executable)

_PASS = 0
_FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f"\n        {detail}"
        print(msg)


# ---------------------------------------------------------------------------
# build_plan: chosen_approach spec resolution (audit 2026-07-02)
# ---------------------------------------------------------------------------

def test_build_plan_resolves_chosen_candidate() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-1
    # coder.md promises chosen_approach as {id, summary, sketch, rationale};
    # the report top-level field is a bare id - build_plan must resolve it
    # from the generator deliberation_log step so the Coder is not handed an
    # id-only spec its own thin-sketch rule marks blocked.
    report = {
        "chosen_approach": "approach_a",
        "success_criterion": "sc", "verification": "v",
        "deliberation_log": [
            {"step": "generator", "candidates": [
                {"id": "approach_a", "summary": "s", "sketch": "sk", "rationale": "r"},
                {"id": "do_nothing", "summary": "n", "sketch": "-", "rationale": "-"},
            ]},
        ],
    }
    plan = build_plan(report)
    check(
        "build_plan: chosen resolved to the full candidate object",
        isinstance(plan["spec"]["chosen_approach"], dict)
        and plan["spec"]["chosen_approach"].get("sketch") == "sk",
        repr(plan["spec"]["chosen_approach"]),
    )
    check("build_plan: chosen_resolved flag true", plan["spec"]["chosen_resolved"] is True)
    bare = build_plan({"chosen_approach": "x", "success_criterion": "sc", "verification": "v"})
    check(
        "build_plan: unresolvable id falls back to the bare string + flag false",
        bare["spec"]["chosen_approach"] == "x" and bare["spec"]["chosen_resolved"] is False,
        repr(bare["spec"]),
    )


# ---------------------------------------------------------------------------
# REGRESSION: single-line def
# ---------------------------------------------------------------------------

def test_single_line_def() -> None:
    source = textwrap.dedent("""\
        def f(x):
            return x + 1
    """)
    result = _stub_bodies(source, MARKER)
    lines = result.splitlines()

    # Line 0 = "def f(x):" — unchanged
    check(
        "single-line: header line preserved",
        lines[0] == "def f(x):",
        repr(lines[0]),
    )
    # Line 1 = "    raise NotImplementedError" — stub at indent+4 (0+4=4 spaces)
    expected_stub = "    " + MARKER
    check(
        "single-line: stub inserted at indent+4 on line 1",
        lines[1] == expected_stub,
        repr(lines[1]),
    )
    # Exactly ONE stub line was inserted
    stub_count = sum(1 for l in lines if MARKER in l)
    check(
        "single-line: exactly one stub line total",
        stub_count == 1,
        f"found {stub_count}",
    )


# ---------------------------------------------------------------------------
# REGRESSION: async def single-line
# ---------------------------------------------------------------------------

def test_async_def_single_line() -> None:
    source = textwrap.dedent("""\
        async def g():
            pass
    """)
    result = _stub_bodies(source, MARKER)
    lines = result.splitlines()

    check(
        "async single-line: header preserved",
        lines[0] == "async def g():",
        repr(lines[0]),
    )
    expected_stub = "    " + MARKER
    check(
        "async single-line: stub at indent+4 on line 1",
        lines[1] == expected_stub,
        repr(lines[1]),
    )


# ---------------------------------------------------------------------------
# REGRESSION: one-line compound def (gate-defeat bug)
# `def f(x): return x + 1` was misread as a multi-line header opener — it set
# in_header, stole the NEXT def's closing ':', and left its own body live, so a
# one-liner impl passed the RED gate unstubbed. These exercise the real idiom
# behaviorally (exec + call), which the two-line test_single_line_def did not.
# ---------------------------------------------------------------------------

def _raises_not_implemented(fn, *args) -> bool:
    try:
        fn(*args)
    except NotImplementedError:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


def test_one_line_compound_def() -> None:
    source = textwrap.dedent("""\
        def foo(x): return x + 1
        def bar(y):
            return y * 2
    """)
    stubbed = _stub_bodies(source, MARKER)
    ns: dict = {}
    try:
        exec(compile(stubbed, "<stub>", "exec"), ns)  # noqa: S102
    except SyntaxError as exc:
        check("one-line compound: stubbed source compiles", False, str(exc))
        return
    check("one-line compound: stubbed source compiles", True)
    check(
        "one-line compound: foo() raises after stub (inline body neutralized)",
        _raises_not_implemented(ns["foo"], 3),
        repr(stubbed),
    )
    check(
        "one-line compound: sibling bar() still stubbed (colon not stolen)",
        _raises_not_implemented(ns["bar"], 3),
        repr(stubbed),
    )


def test_one_line_method() -> None:
    source = textwrap.dedent("""\
        class C:
            def val(self): return 42
    """)
    stubbed = _stub_bodies(source, MARKER)
    check(
        "one-line method: inline body dropped",
        "return 42" not in stubbed,
        repr(stubbed),
    )
    ns: dict = {}
    try:
        exec(compile(stubbed, "<stub>", "exec"), ns)  # noqa: S102
    except SyntaxError as exc:
        check("one-line method: stubbed source compiles", False, str(exc))
        return
    check(
        "one-line method: C().val() raises after stub",
        _raises_not_implemented(ns["C"]().val),
    )


# ---------------------------------------------------------------------------
# NEW: multi-line def header
# ---------------------------------------------------------------------------

def test_multiline_def_header() -> None:
    source = textwrap.dedent("""\
        def foo(
            a, b
        ):
            return a + b
    """)
    result = _stub_bodies(source, MARKER)
    lines = result.splitlines()

    # The three header lines should be present in order
    check(
        "multi-line: 'def foo(' line present",
        any("def foo(" in l for l in lines),
        str(lines),
    )
    check(
        "multi-line: '    a, b' line present",
        any(l.strip() == "a, b" for l in lines),
        str(lines),
    )
    check(
        "multi-line: '):' line present",
        any(l.strip() == "):" for l in lines),
        str(lines),
    )

    # Stub must NOT be inserted after "def foo(" (line 0);
    # it must appear AFTER the "):" line.
    closing_idx = next(i for i, l in enumerate(lines) if l.strip() == "):")
    check(
        "multi-line: stub not inserted after first def line",
        lines[1].strip() != MARKER,
        repr(lines[1]),
    )
    stub_line = lines[closing_idx + 1] if closing_idx + 1 < len(lines) else ""
    check(
        "multi-line: stub inserted immediately after closing '):'",
        MARKER in stub_line,
        repr(stub_line),
    )

    # Stub indentation: def is at column 0, so stub must be at 4 spaces
    expected_stub = "    " + MARKER
    check(
        "multi-line: stub indented at def-indent+4 (4 spaces)",
        stub_line == expected_stub,
        repr(stub_line),
    )

    # Only one stub line total
    stub_count = sum(1 for l in lines if MARKER in l)
    check(
        "multi-line: exactly one stub line total",
        stub_count == 1,
        f"found {stub_count}",
    )


# ---------------------------------------------------------------------------
# NEW: stub actually raises — marker lands in body for multi-line case
# ---------------------------------------------------------------------------

def test_multiline_stub_is_executable() -> None:
    """The stubbed source, when exec'd, must raise on calling foo()."""
    source = textwrap.dedent("""\
        def foo(
            a,
            b,
        ):
            return a + b
    """)
    stubbed = _stub_bodies(source, MARKER)

    # exec in an isolated namespace
    ns: dict = {}
    try:
        exec(compile(stubbed, "<stubbed>", "exec"), ns)  # noqa: S102
    except SyntaxError as exc:
        check("multi-line exec: stubbed source compiles", False, str(exc))
        return

    check("multi-line exec: stubbed source compiles", True)

    raised = False
    try:
        ns["foo"](1, 2)
    except NotImplementedError:
        raised = True
    except Exception as exc:  # noqa: BLE001
        check("multi-line exec: foo() raises NotImplementedError", False, str(exc))
        return

    check("multi-line exec: foo() raises NotImplementedError", raised)


# ---------------------------------------------------------------------------
# NEW: indented multi-line def (method inside class)
# ---------------------------------------------------------------------------

def test_multiline_def_indented() -> None:
    """Method inside a class: stub must use method-indent+4."""
    source = textwrap.dedent("""\
        class C:
            def bar(
                self,
                x,
            ):
                return x
    """)
    result = _stub_bodies(source, MARKER)
    lines = result.splitlines()

    closing_idx = next(i for i, l in enumerate(lines) if l.strip() == "):")
    stub_line = lines[closing_idx + 1] if closing_idx + 1 < len(lines) else ""

    # "    def bar(" is at 4-space indent, so stub should be at 8 spaces
    expected_stub = "        " + MARKER
    check(
        "indented multi-line: stub at method-indent+4 (8 spaces)",
        stub_line == expected_stub,
        repr(stub_line),
    )


# ---------------------------------------------------------------------------
# NEW: verify_red_green multi-target gate (fan-out: stub ALL impl files)
#
# Hole (deductively identified post-#463, fixed 2026-06-29; not an observed CI
# failure): the gate stubbed a single --target. When the Coder fan-out writes N
# implementation files, stubbing only one leaves the other N-1 live, so the RED
# run can stay GREEN (the suite is still pinned by an
# un-stubbed file) and the gate spuriously fails a correctly-tested change.
# Stubbing every target at once makes the RED run reliably break behavior.
# ---------------------------------------------------------------------------


def _gate_fixture(tmp: Path) -> str:
    """Two impl files + a test that exercises only impl_core. Returns the test cmd.

    impl_extra is a fan-out sibling that no test imports — stubbing it alone
    cannot turn the suite RED, which is exactly the single-target hole.
    """
    (tmp / "impl_core.py").write_text(
        textwrap.dedent("""\
            def answer():
                return 42
        """),
        encoding="utf-8",
    )
    (tmp / "impl_extra.py").write_text(
        textwrap.dedent("""\
            def unused():
                return 0
        """),
        encoding="utf-8",
    )
    (tmp / "test_core.py").write_text(
        textwrap.dedent("""\
            from impl_core import answer
            assert answer() == 42
        """),
        encoding="utf-8",
    )
    return f"{_PY} test_core.py"


def _run_gate_in(tmp: Path, targets) -> dict:
    """Run verify_red_green with cwd set to tmp (the gate runs the suite from cwd)."""
    cmd = _gate_fixture(tmp)
    prev = os.getcwd()
    os.chdir(tmp)
    try:
        return verify_red_green(cmd, targets)
    finally:
        os.chdir(prev)


def test_gate_multi_target_stubs_all() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-3
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        result = _run_gate_in(tmp, ["impl_core.py", "impl_extra.py"])
        check("multi-target: green_ok", result.get("green_ok") is True, repr(result))
        check(
            "multi-target: red_ok (stubbing all impl files breaks the suite)",
            result.get("red_ok") is True,
            repr(result),
        )
        check("multi-target: gate_passed", result.get("gate_passed") is True, repr(result))
        # restore-all: both files back to original after the run
        check(
            "multi-target: impl_core restored",
            "return 42" in (tmp / "impl_core.py").read_text(encoding="utf-8"),
            repr((tmp / "impl_core.py").read_text(encoding="utf-8")),
        )
        check(
            "multi-target: impl_extra restored",
            "return 0" in (tmp / "impl_extra.py").read_text(encoding="utf-8"),
            repr((tmp / "impl_extra.py").read_text(encoding="utf-8")),
        )


def test_gate_single_wrong_target_misses_sibling() -> None:
    """The hole: stubbing one untested sibling leaves the suite GREEN → gate fails."""
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-3
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        result = _run_gate_in(tmp, ["impl_extra.py"])
        check("single-wrong: green_ok", result.get("green_ok") is True, repr(result))
        check(
            "single-wrong: red_ok is False (untested sibling stub can't break suite)",
            result.get("red_ok") is False,
            repr(result),
        )
        check("single-wrong: gate_passed False", result.get("gate_passed") is False, repr(result))


def test_gate_single_string_backward_compat() -> None:
    """A bare string target (legacy single-file call) still works."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        result = _run_gate_in(tmp, "impl_core.py")
        check(
            "single-string: gate_passed True (str accepted, not iterated char-wise)",
            result.get("gate_passed") is True,
            repr(result),
        )


def test_gate_missing_target_errors() -> None:
    """Any missing target → error dict, gate not passed, no crash."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        result = _run_gate_in(tmp, ["impl_core.py", "does_not_exist.py"])
        check("missing-target: gate_passed False", result.get("gate_passed") is False, repr(result))
        check("missing-target: error present", "error" in result, repr(result))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def test_multiline_header_trailing_comment() -> None:
    # REGRESSION (audit 2026-07-02): a multi-line header whose closing `):` line
    # carries a trailing comment (`):  # noqa`) was never recognized as closing
    # the header, so the body stayed live — RED == GREEN and the gate spuriously
    # failed a correctly-tested change with "tests do not pin behavior".
    source = textwrap.dedent("""\
        def helper(
            a,
        ):  # noqa
            return a
    """)
    result = _stub_bodies(source, MARKER)
    check(
        "multiline+comment: stub inserted (source changed)",
        result != source,
        "source unchanged — trailing comment hid the header close",
    )
    stub_count = sum(1 for l in result.splitlines() if MARKER in l)
    check(
        "multiline+comment: exactly one stub line total",
        stub_count == 1,
        f"found {stub_count}",
    )
    ns: dict = {}
    exec(result, ns)  # noqa: S102 — exercising the stubbed source behaviorally
    check(
        "multiline+comment: stubbed helper actually raises",
        _raises_not_implemented(ns["helper"], 5),
        "helper(5) returned a value instead of raising",
    )


_SCRIPT = Path(__file__).resolve().parent.parent / "consilium" / "scripts" / "implement_pipeline.py"


def _run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        input=stdin, capture_output=True, text=True, encoding="utf-8",
    )


def test_build_plan_shape() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-1
    plan = build_plan({
        "chosen_approach": "x", "success_criterion": "sc",
        "verification": "v",
    })
    check(
        "plan shape: spec/sequence/roles/rules keys present",
        {"spec", "sequence", "roles", "rules"} <= set(plan),
        repr(sorted(plan)),
    )
    check(
        "plan shape: coder/test_writer/reviewer roles each carry exists flag",
        [r["role"] for r in plan["roles"]]
        == ["coder", "test_writer", "reviewer"]
        and all(isinstance(r["exists"], bool) for r in plan["roles"]),
        repr(plan["roles"]),
    )


def test_cli_no_pipeline_exits_1() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-2
    for chosen in ("do_nothing", "skipped"):
        proc = _run_cli(stdin=json.dumps({"chosen_approach": chosen}))
        check(
            f"no-pipeline ({chosen}): exit 1",
            proc.returncode == 1,
            f"rc={proc.returncode} stderr={proc.stderr!r}",
        )
        check(
            f"no-pipeline ({chosen}): message printed to stdout",
            bool(proc.stdout.strip()),
            repr(proc.stdout),
        )


def test_gate_fails_when_real_suite_fails() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-3
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "impl.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        failing = f'{_PY} -c "import sys; sys.exit(1)"'
        result = _in_dir(d, lambda: verify_red_green(failing, "impl.py"))
        check(
            "gate: green_ok False when the real suite fails",
            result.get("green_ok") is False,
            repr(result),
        )
        check(
            "gate: gate_passed False even though the stubbed run is red",
            result.get("gate_passed") is False,
            repr(result),
        )


def _in_dir(path, fn):
    prev = os.getcwd()
    os.chdir(path)
    try:
        return fn()
    finally:
        os.chdir(prev)


def test_gate_never_writes_stubs_into_the_original() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-4
    # The RED run happens in a disposable copy: the original is byte-identical
    # at every moment, so a crash cannot leave it stubbed.
    original = "def f():\n    return 1\n"
    with tempfile.TemporaryDirectory() as d:
        impl = Path(d) / "impl.py"
        impl.write_text(original, encoding="utf-8")
        seen: list[tuple[str, str, str]] = []

        def fake_run(_cmd: str, cwd=None):
            here = Path(cwd) if cwd else Path.cwd()
            seen.append((
                str(here.resolve()),
                impl.read_text(encoding="utf-8"),
                (here / "impl.py").read_text(encoding="utf-8"),
            ))
            if len(seen) == 1:
                return 0, ""
            raise RuntimeError("stubbed run crashed")

        real_run = _ip._run
        _ip._run = fake_run
        raised = False
        try:
            _in_dir(d, lambda: verify_red_green("ignored", "impl.py"))
        except RuntimeError:
            raised = True
        finally:
            _ip._run = real_run
        check("isolation: the crash propagated", raised)
        check(
            "isolation: RED ran in a different directory",
            len(seen) == 2 and seen[1][0] != seen[0][0],
            repr(seen),
        )
        check(
            "isolation: stub existed only in the copy",
            len(seen) == 2 and MARKER in seen[1][2] and MARKER not in seen[1][1],
            repr(seen),
        )
        check(
            "isolation: original unchanged after the crash",
            impl.read_text(encoding="utf-8") == original,
            repr(impl.read_text(encoding="utf-8")),
        )


def test_gate_original_survives_sigkill_during_red() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-4
    # Real process kill (no finally block runs) while the RED suite is mid-run.
    original = "def f():\n    return 1\n"
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        tmp = Path(d)
        (tmp / "impl.py").write_text(original, encoding="utf-8")
        (tmp / "hang.py").write_text(textwrap.dedent("""\
            import pathlib, sys, time
            import impl
            try:
                impl.f()
            except NotImplementedError:
                flag = pathlib.Path(sys.argv[1])
                flag.write_text("x")
                for _ in range(150):
                    if pathlib.Path(str(flag) + ".stop").exists():
                        break
                    time.sleep(0.1)
                raise
        """), encoding="utf-8")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as fd:
            flag = Path(fd) / "red_started"
            proc = subprocess.Popen(
                [sys.executable, str(_SCRIPT), "--verify-gate",
                 "--test-cmd", f"{_PY} hang.py {shlex.quote(str(flag))}",
                 "--target", "impl.py"],
                cwd=tmp, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(200):
                    if flag.exists() or proc.poll() is not None:
                        break
                    time.sleep(0.1)
                started = flag.exists()
                proc.kill()
                proc.wait()
            finally:
                Path(str(flag) + ".stop").write_text("x")
            check("sigkill: RED suite had started", started)
            check(
                "sigkill: original impl.py is byte-identical",
                (tmp / "impl.py").read_text(encoding="utf-8") == original,
                repr((tmp / "impl.py").read_text(encoding="utf-8")),
            )


def test_stub_bodies_two_space_indent_compiles() -> None:
    # REGRESSION: the stub was always inserted at header indent + 4, so a body
    # indented by 2 gave "unindent does not match" -> an invalid mutant.
    for label, source in (
        ("function", "def f():\n  return 1\n"),
        ("method", "class A:\n  def m(self):\n    return 1\n"),
        ("tabs", "def f():\n\treturn 1\n"),
        ("deep", "def f():\n        return 1\n"),
    ):
        stubbed = _stub_bodies(source, MARKER)
        try:
            compile(stubbed, "<stub>", "exec")
            ok, detail = True, ""
        except SyntaxError as exc:
            ok, detail = False, f"{exc!r}\n{stubbed}"
        check(f"two-space stub compiles ({label})", ok, detail)


def _gate_in_fixture(files: dict[str, str], cmd: str, target: str = "impl.py") -> dict:
    with tempfile.TemporaryDirectory() as d:
        for name, text in files.items():
            (Path(d) / name).write_text(text, encoding="utf-8")
        return _in_dir(d, lambda: verify_red_green(cmd, target))


def test_gate_compile_only_check_is_not_red() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-3
    # A suite that only compiles the file never exercises behavior: the valid
    # stub compiles, so it stays GREEN and the gate must fail.
    result = _gate_in_fixture(
        {"impl.py": "def f():\n  return 1\n"},
        f"{_PY} -m py_compile impl.py",
    )
    check("compile-only: gate_passed False", result.get("gate_passed") is False, repr(result))
    check("compile-only: red_ok False", result.get("red_ok") is False, repr(result))


def test_gate_behavioral_test_on_two_space_file_passes() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-3
    result = _gate_in_fixture(
        {"impl.py": "def f():\n  return 1\n"},
        f'{_PY} -c "import impl; assert impl.f() == 1"',
    )
    check("two-space behavioral: gate_passed", result.get("gate_passed") is True, repr(result))


def test_gate_non_behavioral_failure_is_not_red() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-3
    # Non-zero exit that is not the stub firing (here: the suite bails out on
    # seeing a modified file) is a technical error, not a RED.
    result = _gate_in_fixture(
        {
            "impl.py": "def f():\n    return 1\n",
            "check_stub.py": (
                "import sys\n"
                "if 'Not' + 'Implemented' in open('impl.py').read():\n"
                "    sys.exit('tampered')\n"
            ),
        },
        f"{_PY} check_stub.py",
    )
    check("non-behavioral: red_ok False", result.get("red_ok") is False, repr(result))
    check("non-behavioral: gate_passed False", result.get("gate_passed") is False, repr(result))


def test_gate_invalid_mutant_is_rejected_before_running() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-3
    real_stub = _ip._stub_bodies
    _ip._stub_bodies = lambda source, marker: "def f(:\n"
    try:
        result = _gate_in_fixture(
            {"impl.py": "def f():\n    return 1\n"},
            f'{_PY} -c "import impl; assert impl.f() == 1"',
        )
    finally:
        _ip._stub_bodies = real_stub
    check("invalid-mutant: gate_passed False", result.get("gate_passed") is False, repr(result))
    check(
        "invalid-mutant: error names the syntax problem",
        "syntax" in str(result.get("error", "")).lower(),
        repr(result),
    )


def test_gate_unrunnable_test_command_is_an_error_not_a_crash() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-3
    result = _gate_in_fixture(
        {"impl.py": "def f():\n    return 1\n"}, "no_such_binary_xyz_123"
    )
    check("unrunnable: gate_passed False", result.get("gate_passed") is False, repr(result))
    check("unrunnable: error present", "error" in result, repr(result))


def test_gate_target_outside_cwd_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
        impl = Path(other) / "impl.py"
        impl.write_text("def f():\n    return 1\n", encoding="utf-8")
        result = _in_dir(d, lambda: verify_red_green(f"{_PY} -c pass", str(impl)))
        check("outside-cwd: gate_passed False", result.get("gate_passed") is False, repr(result))
        check("outside-cwd: error present", "error" in result, repr(result))


def test_cli_verify_gate_missing_args_exits_2() -> None:
    # verifies: CONSILIUM-IMPLEMENT-PIPELINE-001#CASE-5
    for label, args in (
        ("neither flag", ["--verify-gate"]),
        ("no --target", ["--verify-gate", "--test-cmd", "x"]),
        ("no --test-cmd", ["--verify-gate", "--target", "x.py"]),
    ):
        proc = _run_cli(*args)
        check(
            f"verify-gate ({label}): exit 2",
            proc.returncode == 2,
            f"rc={proc.returncode}",
        )
        check(
            f"verify-gate ({label}): error message on stderr",
            "--verify-gate needs" in proc.stderr,
            repr(proc.stderr),
        )


def main() -> None:
    print("=== test_implement_pipeline ===")
    test_single_line_def()
    test_async_def_single_line()
    test_one_line_compound_def()
    test_one_line_method()
    test_multiline_def_header()
    test_multiline_header_trailing_comment()
    test_multiline_stub_is_executable()
    test_multiline_def_indented()
    test_gate_multi_target_stubs_all()
    test_gate_single_wrong_target_misses_sibling()
    test_gate_single_string_backward_compat()
    test_gate_missing_target_errors()
    test_build_plan_resolves_chosen_candidate()
    test_build_plan_shape()
    test_cli_no_pipeline_exits_1()
    test_gate_fails_when_real_suite_fails()
    test_gate_never_writes_stubs_into_the_original()
    test_gate_original_survives_sigkill_during_red()
    test_stub_bodies_two_space_indent_compiles()
    test_gate_compile_only_check_is_not_red()
    test_gate_behavioral_test_on_two_space_file_passes()
    test_gate_non_behavioral_failure_is_not_red()
    test_gate_invalid_mutant_is_rejected_before_running()
    test_gate_unrunnable_test_command_is_an_error_not_a_crash()
    test_gate_target_outside_cwd_is_rejected()
    test_cli_verify_gate_missing_args_exits_2()

    total = _PASS + _FAIL
    print(f"\n{_PASS}/{total} passed, {_FAIL} failed")
    sys.exit(0 if _FAIL == 0 else 1)


if __name__ == "__main__":
    main()
