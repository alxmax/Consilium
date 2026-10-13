"""Standalone tests for render_feedback_html + feedback.py HTML parser.

Run: python scripts/test_feedback_html.py
Exit 0 = all pass; exit 1 = one or more failures (all tests run; failures listed).
"""
# tested-by: CONSILIUM-RENDER-FEEDBACK-HTML-001
# tested-by: CONSILIUM-FEEDBACK-001
# tested-by: CONSILIUM-MARK-OUTCOME-001
# tested-by: CONSILIUM-MEMORY-001
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "consilium"  # the shipped plugin (SKILL.md, modes/, prompts/, scripts/)
sys.path.insert(0, str(ROOT / "scripts"))

import render_feedback_html as rfh  # noqa: E402


def test_render_empty_entries_produces_skeleton():
    html = rfh.render(entries=[], runs_dir=ROOT / "runs")
    assert "<!doctype html>" in html
    assert "Consilium feedback" in html
    assert "<tbody>" in html and "</tbody>" in html
    assert "0 entries" in html


def test_render_single_legacy_entry_no_drill():
    e = rfh.Entry(
        date="2026-05-11",
        context="audit-reduction",
        chosen="nuke_orphans_and_stale_readme",
        outcome="PEND",
        note="5 cand, conf=0.63",
        run_path=None,
    )
    html_out = rfh.render([e], runs_dir=ROOT / "runs")
    assert "1 entries" in html_out
    assert "2026-05-11" in html_out
    assert "nuke_orphans_and_stale_readme" in html_out
    assert "PEND" in html_out
    assert 'class="outcome PEND"' in html_out
    assert "no detailed run data" in html_out
    assert 'class="entry"' in html_out
    assert 'class="drill"' in html_out


def test_render_escapes_html_in_user_text():
    e = rfh.Entry(
        date="2026-05-11",
        context="<script>alert(1)</script>",
        chosen="x",
        outcome="OK",
        note="& \"quoted\"",
        run_path=None,
    )
    html_out = rfh.render([e], runs_dir=ROOT / "runs")
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "&amp;" in html_out


def test_render_drill_from_real_run_file():
    # Use a synthetic run JSON in a temp directory so the test has no dependency
    # on any tracked file in runs/.
    synthetic_run = {
        "success_criterion": "Click pe sageata Rerun din topbar",
        "chosen_approach": "disable_when_unreachable",
        "confidence": 0.62,
        "deliberation_log": [
            {
                "step": "generator",
                "candidates": [
                    {"id": "do_nothing", "summary": "Accept current state.", "sketch": "Baseline."},
                    {"id": "disable_when_unreachable", "summary": "Probe disables Rerun.", "sketch": "~20 lines."},
                    {"id": "adversarial_url_protocol_handler", "summary": "Register protocol.", "sketch": "Stress test."},
                ],
            },
            {
                "step": "control",
                "verdicts": [
                    {"id": "do_nothing", "valid": True, "issues": [], "tests_to_write": []},
                    {
                        "id": "disable_when_unreachable",
                        "valid": True,
                        "issues": [],
                        "tests_to_write": [
                            {"name": "probe_success_enables", "assert": "200 -> opacity=1"},
                        ],
                    },
                    {
                        "id": "adversarial_url_protocol_handler",
                        "valid": False,
                        "issues": [{"category": "logic", "detail": "Registry irreversible."}],
                        "tests_to_write": [],
                    },
                ],
            },
            {
                "step": "conservator",
                "scores": [
                    {
                        "id": "disable_when_unreachable",
                        "risk_score": 0.14,
                        "factors": {"diff_size": 0.1, "scope_drift": 0.05, "regression_risk": 0.1, "reversibility": 0.2},
                    },
                ],
            },
            {
                "step": "aggregate",
                "result": {"vetoed": []},
            },
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        runs_subdir = td_path / "runs"
        runs_subdir.mkdir()
        run_file = runs_subdir / "synthetic_run.json"
        run_file.write_text(json.dumps(synthetic_run), encoding="utf-8")

        e = rfh.Entry(
            date="2026-05-11",
            context="Click pe sageata Rerun din topbar",
            chosen="disable_when_unreachable",
            outcome="PEND",
            note="3 cand, 0 vetoed, conf=0.62",
            run_path="runs/synthetic_run.json",
        )
        html_out = rfh.render([e], runs_dir=runs_subdir)

    # Generator section
    assert "Generator" in html_out
    assert "do_nothing" in html_out
    assert "disable_when_unreachable" in html_out
    # CHOSEN badge on the picked candidate
    assert "CHOSEN" in html_out
    # Control section: valid/invalid badges
    assert ">valid<" in html_out
    assert ">invalid<" in html_out
    # Tests rendered
    assert "probe_success_enables" in html_out
    # Conservator section: factor breakdown
    assert "diff:" in html_out
    assert "scope:" in html_out
    assert "0.14" in html_out  # disable_when_unreachable risk_score
    assert "no detailed run data" not in html_out


def test_render_drill_tolerates_string_issues():
    # Regression: 2026-06-10 — a run with control issues/tests_to_write as bare
    # strings (not dicts) crashed _ctrl_panel with AttributeError and blocked
    # every subsequent log_feedback append. Found when a BOM-corrupted run was
    # repaired and its drill-down rendered for the first time.
    synthetic_run = {
        "success_criterion": "x",
        "chosen_approach": "a",
        "confidence": 0.5,
        "deliberation_log": [
            {
                "step": "control",
                "verdicts": [
                    {
                        "id": "a",
                        "valid": False,
                        "issues": ["plain string issue"],
                        "tests_to_write": ["plain string test"],
                    },
                ],
            },
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        runs_subdir = td_path / "runs"
        runs_subdir.mkdir()
        (runs_subdir / "string_issues.json").write_text(
            json.dumps(synthetic_run), encoding="utf-8"
        )
        e = rfh.Entry(
            date="2026-06-10",
            context="x",
            chosen="a",
            outcome="PEND",
            note="",
            run_path="runs/string_issues.json",
        )
        html_out = rfh.render([e], runs_dir=runs_subdir)
    assert "plain string issue" in html_out
    assert "plain string test" in html_out


def test_render_drill_missing_run_file_falls_back_to_stub():
    e = rfh.Entry(
        date="2026-05-11",
        context="x",
        chosen="y",
        outcome="PEND",
        note="",
        run_path="runs/does_not_exist.json",
    )
    html_out = rfh.render([e], runs_dir=ROOT / "runs")
    assert "no detailed run data" in html_out


def test_parse_feedback_roundtrip_html():
    # Build entries, render to HTML, parse back, expect same fields.
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402

    original = [
        rfh.Entry(date="2026-05-11", context="ctx one", chosen="approach_a",
                  outcome="OK", note="5 cand, conf=0.65"),
        rfh.Entry(date="2026-05-12", context="ctx <two> & special",
                  chosen="approach_b", outcome="OVR",
                  note="override=alt; conf=0.43"),
    ]
    html_out = rfh.render(original, runs_dir=ROOT / "runs")

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_out)
        tmp_path = Path(f.name)
    try:
        parsed = feedback.parse_feedback(tmp_path)
    finally:
        tmp_path.unlink()

    assert len(parsed) == 2, f"got {len(parsed)} entries, want 2"
    assert parsed[0]["date"] == "2026-05-11"
    assert parsed[0]["context"] == "ctx one"
    assert parsed[0]["chosen"] == "approach_a"
    assert parsed[0]["outcome"] == "OK"
    assert "5 cand" in parsed[0]["note"]
    assert parsed[1]["context"] == "ctx <two> & special"  # unescaped on parse
    assert parsed[1]["outcome"] == "OVR"


def test_parse_feedback_returns_empty_for_missing_file():
    # verifies: CONSILIUM-FEEDBACK-001#CASE-1
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402
    assert feedback.parse_feedback(Path("/nonexistent/FEEDBACK.html")) == []


def test_log_feedback_appends_html_entry():
    import subprocess
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402

    with tempfile.TemporaryDirectory() as td:
        feedback_path = Path(td) / "FEEDBACK.html"
        # Pre-populate with one entry via render.
        e0 = rfh.Entry(date="2026-05-01", context="pre", chosen="x",
                       outcome="OK", note="seed")
        feedback_path.write_text(rfh.render([e0], runs_dir=ROOT / "runs"), encoding="utf-8")

        report = {
            "success_criterion": "fix the test",
            "chosen_approach": "approach_a",
            "confidence": 0.81,
            "telemetry": {"mode": "parallel"},
            "deliberation_log": [{"step": "generator", "candidates": [{"id": "a"}, {"id": "b"}]}],
        }
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "log_feedback.py"),
             "--feedback", str(feedback_path),
             "--outcome", "OK", "--confirmed"],
            input=json.dumps(report).encode("utf-8"),
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"

        parsed = feedback.parse_feedback(feedback_path)
        assert len(parsed) == 2, f"expected 2 entries (1 seed + 1 appended), got {len(parsed)}"
        assert parsed[1]["chosen"] == "approach_a"
        assert parsed[1]["outcome"] == "OK"


def test_log_feedback_dedup_skips_duplicate():
    """Appending the same entry twice must not create a duplicate row."""
    import subprocess
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402

    report = {
        "success_criterion": "dedup test",
        "chosen_approach": "approach_x",
        "confidence": 0.85,
        "telemetry": {"mode": "sequential"},
        "deliberation_log": [],
    }
    with tempfile.TemporaryDirectory() as td:
        feedback_path = Path(td) / "FEEDBACK.html"
        common_args = [
            sys.executable, str(ROOT / "scripts" / "log_feedback.py"),
            "--feedback", str(feedback_path),
            "--outcome", "OK",
            "--confirmed",
            "--force-override",
        ]
        input_bytes = json.dumps(report).encode("utf-8")
        r1 = subprocess.run(common_args, input=input_bytes, capture_output=True, check=False)
        assert r1.returncode == 0, f"first append failed: {r1.stderr.decode()}"
        r2 = subprocess.run(common_args, input=input_bytes, capture_output=True, check=False)
        # Second call should exit 3 (duplicate) not 0.
        assert r2.returncode == 3, f"expected exit 3 (duplicate), got {r2.returncode}"
        parsed = feedback.parse_feedback(feedback_path)
        assert len(parsed) == 1, f"expected 1 row after dedup, got {len(parsed)}"


def test_log_feedback_upgrades_pend_in_place():
    """A second log with the same --run-path but a different outcome upgrades the
    existing row in place (close-the-loop), instead of skipping it as a duplicate."""
    import subprocess
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402

    report = {
        "success_criterion": "close-the-loop test",
        "chosen_approach": "approach_y",
        "confidence": 0.62,
        "telemetry": {"mode": "sequential"},
        "deliberation_log": [],
    }
    with tempfile.TemporaryDirectory() as td:
        feedback_path = Path(td) / "FEEDBACK.html"
        (Path(td) / "runs").mkdir()
        base = [
            sys.executable, str(ROOT / "scripts" / "log_feedback.py"),
            "--feedback", str(feedback_path),
            "--run-path", "runs/loop.json",
        ]
        inp = json.dumps(report).encode("utf-8")
        r1 = subprocess.run(base + ["--outcome", "PEND_HEADLESS"], input=inp, capture_output=True, check=False)
        assert r1.returncode == 0, f"first log failed: {r1.stderr.decode()}"
        # Same run, same outcome -> duplicate skip (exit 3).
        r2 = subprocess.run(base + ["--outcome", "PEND_HEADLESS"], input=inp, capture_output=True, check=False)
        assert r2.returncode == 3, f"expected exit 3 (duplicate), got {r2.returncode}"
        # Same run, NEW outcome -> upgrade in place (exit 0, no new row).
        r3 = subprocess.run(base + ["--outcome", "OK", "--confirmed", "--force-override"], input=inp, capture_output=True, check=False)
        assert r3.returncode == 0, f"in-place upgrade failed: {r3.stderr.decode()}"
        parsed = feedback.parse_feedback(feedback_path)
        assert len(parsed) == 1, f"expected 1 row after in-place upgrade, got {len(parsed)}"
        assert parsed[0]["outcome"] == "OK", f"expected OK after upgrade, got {parsed[0]['outcome']}"


def test_log_feedback_ok_requires_confirmed():
    """OK is a verified outcome: without --confirmed log_feedback refuses it and
    writes nothing; with --confirmed the row carries the [confirmed] marker."""
    import subprocess
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402

    report = {
        "success_criterion": "confirmed-gate test",
        "chosen_approach": "approach_c",
        "confidence": 0.9,
        "telemetry": {"mode": "sequential"},
        "deliberation_log": [],
    }
    with tempfile.TemporaryDirectory() as td:
        feedback_path = Path(td) / "FEEDBACK.html"
        base = [sys.executable, str(ROOT / "scripts" / "log_feedback.py"),
                "--feedback", str(feedback_path), "--outcome", "OK"]
        inp = json.dumps(report).encode("utf-8")
        r1 = subprocess.run(base, input=inp, capture_output=True, check=False)
        assert r1.returncode == 1, f"expected exit 1 without --confirmed, got {r1.returncode}"
        assert b"--confirmed" in r1.stderr
        assert not feedback_path.exists(), "a refused OK must not write the file"
        r2 = subprocess.run(base + ["--confirmed"], input=inp, capture_output=True, check=False)
        assert r2.returncode == 0, f"stderr: {r2.stderr.decode()}"
        parsed = feedback.parse_feedback(feedback_path)
        assert len(parsed) == 1 and parsed[0]["outcome"] == "OK"
        assert "[confirmed]" in parsed[0]["note"]


def test_mark_outcome_closed_unverified_round_trips():
    """CLOSED_UNVERIFIED closes a PEND without the [confirmed] marker, and the row
    survives a later append (an unknown outcome would be dropped by the parser)."""
    import subprocess
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402

    with tempfile.TemporaryDirectory() as td:
        feedback_path = Path(td) / "FEEDBACK.html"
        e = rfh.Entry(date="2026-05-20", context="stale", chosen="approach_s",
                      outcome="PEND", note="3 cand, conf=0.80")
        feedback_path.write_text(rfh.render([e], runs_dir=Path(td) / "runs"), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "mark_outcome.py"),
             "--feedback", str(feedback_path), "--date", "2026-05-20",
             "--chosen", "approach_s", "--outcome", "CLOSED_UNVERIFIED"],
            capture_output=True, check=False,
        )
        assert r.returncode == 0, f"stderr: {r.stderr.decode()}"
        report = {"success_criterion": "next run", "chosen_approach": "approach_n",
                  "confidence": 0.8, "telemetry": {"mode": "sequential"}, "deliberation_log": []}
        r2 = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "log_feedback.py"), "--feedback", str(feedback_path)],
            input=json.dumps(report).encode("utf-8"), capture_output=True, check=False,
        )
        assert r2.returncode == 0, f"stderr: {r2.stderr.decode()}"
        parsed = feedback.parse_feedback(feedback_path)
        assert [p["outcome"] for p in parsed] == ["CLOSED_UNVERIFIED", "PEND"], parsed
        assert "[confirmed]" not in parsed[0]["note"]


def test_mark_outcome_happy_path():
    """mark_outcome updates outcome and annotates note on a matched row."""
    import subprocess
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402

    with tempfile.TemporaryDirectory() as td:
        feedback_path = Path(td) / "FEEDBACK.html"
        e = rfh.Entry(date="2026-05-20", context="mark-test", chosen="approach_z",
                      outcome="PEND", note="5 cand, conf=0.75")
        feedback_path.write_text(rfh.render([e], runs_dir=Path(td) / "runs"), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "mark_outcome.py"),
             "--feedback", str(feedback_path),
             "--date", "2026-05-20",
             "--chosen", "approach_z",
             "--outcome", "BAD",
             "--reason", "broke prod"],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        parsed = feedback.parse_feedback(feedback_path)
        assert len(parsed) == 1
        assert parsed[0]["outcome"] == "BAD"
        assert "outcome_reason=broke prod" in parsed[0]["note"]
        assert "[confirmed]" in parsed[0]["note"]


def test_mark_outcome_auto_suggest_reads_falsifier():
    """--auto-suggest with no explicit --reason pulls the declared falsifier
    (Control's strongest_objection.reason) from the run JSON as the default reason."""
    # verifies: CONSILIUM-MARK-OUTCOME-001#CASE-1
    import subprocess
    sys.path.insert(0, str(ROOT / "scripts"))
    import feedback  # noqa: E402

    with tempfile.TemporaryDirectory() as td:
        feedback_path = Path(td) / "FEEDBACK.html"
        runs_dir = Path(td) / "runs"
        runs_dir.mkdir()

        run_file = runs_dir / "2026-07-07_falsifier-test.json"
        run_file.write_text(json.dumps({
            "chosen_approach": "approach_f",
            "deliberation_log": [
                {"step": "generator", "candidates": [{"id": "approach_f"}]},
                {"step": "control", "verdicts": [{"id": "approach_f", "valid": True}],
                 "strongest_objection": {"target_id": None,
                                         "reason": "wrong if error rate exceeds 2% in week 1"},
                 "no_blocking_defect_attested": True},
                {"step": "aggregate", "scheme": "sequential", "result": {"chosen": "approach_f"}},
            ],
        }), encoding="utf-8")

        # Seed a row whose sidecar maps to the run path.
        e = rfh.Entry(date="2026-07-07", context="falsifier-test", chosen="approach_f",
                      outcome="PEND", note="conf=0.8")
        feedback_path.write_text(rfh.render([e], runs_dir=runs_dir), encoding="utf-8")
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("lf", ROOT / "scripts" / "log_feedback.py")
        assert spec and spec.loader
        lf = _ilu.module_from_spec(spec)
        spec.loader.exec_module(lf)
        fp = lf._fingerprint("2026-07-07", "approach_f", "falsifier-test",
                             run_id=run_file.name)
        (runs_dir / ".run_path_map.json").write_text(
            json.dumps({fp: f"runs/{run_file.name}"}), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "mark_outcome.py"),
             "--feedback", str(feedback_path),
             "--run-path", str(run_file),
             "--outcome", "BAD",
             "--auto-suggest"],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        parsed = feedback.parse_feedback(feedback_path)
        assert len(parsed) == 1
        assert parsed[0]["outcome"] == "BAD"
        assert "wrong if error rate exceeds 2% in week 1" in parsed[0]["note"], \
            f"falsifier not in note: {parsed[0]['note']!r}"

    # explicit --reason must still win over auto-suggest (no falsifier override)
    with tempfile.TemporaryDirectory() as td:
        feedback_path = Path(td) / "FEEDBACK.html"
        runs_dir = Path(td) / "runs"
        runs_dir.mkdir()
        run_file = runs_dir / "2026-07-07_falsifier-test2.json"
        run_file.write_text(json.dumps({
            "deliberation_log": [
                {"step": "control", "verdicts": [],
                 "strongest_objection": {"target_id": None, "reason": "should not appear"}},
            ],
        }), encoding="utf-8")
        e = rfh.Entry(date="2026-07-07", context="falsifier-test2", chosen="approach_g",
                      outcome="PEND", note="conf=0.8")
        feedback_path.write_text(rfh.render([e], runs_dir=runs_dir), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "mark_outcome.py"),
             "--feedback", str(feedback_path),
             "--date", "2026-07-07", "--chosen", "approach_g",
             "--outcome", "BAD",
             "--auto-suggest",
             "--reason", "explicit wins"],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"stderr: {result.stderr.decode()}"
        parsed = feedback.parse_feedback(feedback_path)
        assert "outcome_reason=explicit wins" in parsed[0]["note"]
        assert "should not appear" not in parsed[0]["note"]


def test_main_bom_prefixed_stdin_renders():
    """main() tolerates a leading UTF-8 BOM (PowerShell pipe) instead of crashing."""
    import subprocess
    payload = {"entries": [{"date": "2026-07-04", "context": "bom-test",
                            "chosen": "approach_bom", "outcome": "OK", "note": "x"}]}
    stdin_bytes = b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "render_feedback_html.py")],
        input=stdin_bytes, capture_output=True, check=False,
    )
    assert result.returncode == 0, f"BOM stdin should render, got rc={result.returncode}: {result.stderr.decode(errors='replace')}"
    assert b"approach_bom" in result.stdout


def test_main_malformed_stdin_exits_2():
    """main() exits 2 with a clean message on malformed stdin, not a raw traceback."""
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "render_feedback_html.py")],
        input=b"{not json", capture_output=True, check=False,
    )
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}"
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# feedback.py parser + CLI report  (CONSILIUM-FEEDBACK-001)
# ---------------------------------------------------------------------------

def _tr(*cells: str) -> str:
    return '<tr class="entry">' + "".join(
        f"<td>{c}</td>" for c in cells) + "</tr>"


def _tr_attr(**fields: str) -> str:
    return '<tr class="entry">' + "".join(
        f'<td data-field="{k}">{v}</td>' for k, v in fields.items()) + "</tr>"


def _write_fb(td: str, *rows: str) -> Path:
    p = Path(td) / "FEEDBACK.html"
    p.write_text("<table>" + "".join(rows) + "</table>", encoding="utf-8")
    return p


def _feedback_cli(fb_path: Path, runs_dir: Path, *args: str) -> str:
    """Run feedback.main in-process against a temp journal; return stdout."""
    import contextlib
    import io
    import feedback  # noqa: E402

    saved = (feedback.FEEDBACK, feedback.RUNS)
    feedback.FEEDBACK, feedback.RUNS = fb_path, runs_dir
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            assert feedback.main(list(args)) == 0
    finally:
        feedback.FEEDBACK, feedback.RUNS = saved
    return buf.getvalue()


def test_parse_feedback_all_row_layouts():
    # verifies: CONSILIUM-FEEDBACK-001#CASE-2
    import feedback  # noqa: E402

    with tempfile.TemporaryDirectory() as td:
        p = _write_fb(
            td,
            _tr_attr(date="d1", context="c1", chosen="k1", outcome="OK",
                     note="n1", vote_pattern="2-1"),
            # 8 cells, data-field in shuffled order: attributes win over
            # position (positional reading would see outcome="cc" and drop it)
            _tr_attr(vote_pattern="1-1", note="nn", outcome="BAD", chosen="kk",
                     context="cc", date="dd", tokens="t", chev="x"),
            _tr("+", "d3", "c3", "k3", "OK", "tok", "n3", "3-0"),  # 8-cell
            _tr("+", "d4", "c4", "k4", "OVR", "tok", "n4"),        # 7-cell
            _tr("+", "d5", "c5", "k5", "PEND", "n5"),              # 6-cell
            _tr("+", "d6", "c6", "k6", "OK"),                      # 5 -> skip
        )
        got = [(e["date"], e["chosen"], e["outcome"], e["note"],
                e["vote_pattern"]) for e in feedback.parse_feedback(p)]
    assert got == [
        ("d1", "k1", "OK", "n1", "2-1"),
        ("dd", "kk", "BAD", "nn", "1-1"),
        ("d3", "k3", "OK", "n3", "3-0"),
        ("d4", "k4", "OVR", "n4", ""),
        ("d5", "k5", "PEND", "n5", ""),
    ], got


def test_parse_feedback_drops_unknown_outcome():
    # verifies: CONSILIUM-FEEDBACK-001#CASE-3
    import feedback  # noqa: E402

    with tempfile.TemporaryDirectory() as td:
        p = _write_fb(
            td,
            _tr_attr(date="d1", context="c", chosen="k1", outcome="MAYBE",
                     note=""),
            _tr("+", "d2", "c", "k2", "WIN", "tok", "n"),
            _tr("+", "d3", "c", "k3", "OK", "tok", "n"),
        )
        parsed = feedback.parse_feedback(p)
        assert [e["chosen"] for e in parsed] == ["k3"], parsed
        out = _feedback_cli(p, Path(td) / "runs")
    assert "Total logged uses: 1" in out, out


def test_feedback_cli_recent_and_success_rate():
    # verifies: CONSILIUM-FEEDBACK-001#CASE-4
    with tempfile.TemporaryDirectory() as td:
        rows = [_tr("+", f"d{i}", "c", f"k{i}", o, "tok", "n")
                for i, o in enumerate(
                    ["OK", "BAD", "PEND", "PEND_HEADLESS", "OK"])]
        p = _write_fb(td, *rows)
        runs = Path(td) / "runs"
        everything = _feedback_cli(p, runs)
        recent = _feedback_cli(p, runs, "--recent", "3")
    # PEND / PEND_HEADLESS are outside the denominator: OK 2 / (2 OK + 1 BAD)
    assert "Total logged uses: 5" in everything, everything
    assert "Success rate (excluding PEND): 67%" in everything, everything
    # last 3 = PEND, PEND_HEADLESS, OK -> only OK is rated
    assert "Total logged uses: 3" in recent, recent
    assert "Success rate (excluding PEND): 100%" in recent, recent


def test_feedback_cli_runs_breakdown_both_scheme_shapes():
    # verifies: CONSILIUM-FEEDBACK-001#CASE-5
    with tempfile.TemporaryDirectory() as td:
        p = _write_fb(td, _tr("+", "d1", "c", "k1", "OK", "tok", "n"))
        runs = Path(td) / "runs"
        runs.mkdir()
        (runs / "a.json").write_text(
            json.dumps({"aggregation": {"scheme": "vote"}}), encoding="utf-8")
        (runs / "b.json").write_text(json.dumps({"deliberation_log": [
            {"step": "aggregate", "scheme": "sequential"}]}), encoding="utf-8")
        (runs / "c.json").write_text(json.dumps({"deliberation_log": [
            {"step": "aggregate", "result": {"scheme": "sequential"}}]}),
            encoding="utf-8")
        with_runs = _feedback_cli(p, runs, "--runs")
        without = _feedback_cli(p, runs)
    assert "Deliberation runs on disk: 3" in with_runs, with_runs
    assert "scheme=sequential: 2" in with_runs, with_runs
    assert "scheme=vote: 1" in with_runs, with_runs
    assert "Deliberation runs on disk" not in without, without


# ---------------------------------------------------------------------------
# mark_outcome.py  (CONSILIUM-MARK-OUTCOME-001)
# ---------------------------------------------------------------------------

def _mark(fb: Path, *args: str):
    import subprocess
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "mark_outcome.py"),
         "--feedback", str(fb), *args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


def _seed_pend_row(td: str, outcome: str = "PEND") -> Path:
    fb = Path(td) / "FEEDBACK.html"
    e = rfh.Entry(date="2026-06-01", context="mo-ctx", chosen="approach_m",
                  outcome=outcome, note="conf=0.7")
    fb.write_text(rfh.render([e], runs_dir=Path(td) / "runs"),
                  encoding="utf-8")
    return fb


def test_mark_outcome_dry_run_writes_nothing():
    # verifies: CONSILIUM-MARK-OUTCOME-001#CASE-2
    with tempfile.TemporaryDirectory() as td:
        fb = _seed_pend_row(td)
        before = fb.read_bytes()
        r = _mark(fb, "--date", "2026-06-01", "--chosen", "approach_m",
                  "--outcome", "BAD", "--dry-run")
        assert r.returncode == 0, r.stderr
        assert "matched [0]: 2026-06-01 | approach_m | PEND -> BAD" in r.stdout
        assert "(dry-run; no write)" in r.stdout, r.stdout
        assert fb.read_bytes() == before


def test_mark_outcome_pend_headless_requires_benchmark():
    # verifies: CONSILIUM-MARK-OUTCOME-001#CASE-3
    with tempfile.TemporaryDirectory() as td:
        fb = _seed_pend_row(td)
        before = fb.read_bytes()
        r = _mark(fb, "--date", "2026-06-01", "--chosen", "approach_m",
                  "--outcome", "PEND_HEADLESS")
        assert r.returncode == 1, r.stdout
        assert "--benchmark" in r.stderr, r.stderr
        assert fb.read_bytes() == before


def test_mark_outcome_pend_headless_skips_non_pend_row():
    with tempfile.TemporaryDirectory() as td:
        fb = _seed_pend_row(td, outcome="OK")
        before = fb.read_bytes()
        r = _mark(fb, "--date", "2026-06-01", "--chosen", "approach_m",
                  "--outcome", "PEND_HEADLESS", "--benchmark")
        assert r.returncode == 0, r.stderr
        assert "only PEND rows" in r.stderr, r.stderr
        assert fb.read_bytes() == before


def test_mark_outcome_requires_a_row_selector():
    # verifies: CONSILIUM-MARK-OUTCOME-001#CASE-4
    with tempfile.TemporaryDirectory() as td:
        fb = _seed_pend_row(td)
        before = fb.read_bytes()
        for sel in ([], ["--date", "2026-06-01"], ["--chosen", "approach_m"]):
            r = _mark(fb, *sel, "--outcome", "BAD")
            assert r.returncode == 1, (sel, r.stdout)
            assert "provide --run-path" in r.stderr, r.stderr
        assert fb.read_bytes() == before


def test_mark_outcome_no_match_lists_recent_rows():
    # verifies: CONSILIUM-MARK-OUTCOME-001#CASE-5
    with tempfile.TemporaryDirectory() as td:
        fb = _seed_pend_row(td)
        before = fb.read_bytes()
        r = _mark(fb, "--date", "2099-01-01", "--chosen", "nope",
                  "--outcome", "BAD")
        assert r.returncode == 1, r.stdout
        assert "no row matched" in r.stderr, r.stderr
        assert "last 5 rows" in r.stderr and "approach_m" in r.stderr, r.stderr
        assert fb.read_bytes() == before


def test_mark_outcome_annotate_note_is_idempotent():
    import mark_outcome  # noqa: E402

    once = mark_outcome._annotate_note("conf=0.7", "first")
    twice = mark_outcome._annotate_note(once, "second")
    assert twice == "conf=0.7; [confirmed]; outcome_reason=second", twice
    assert twice.count("[confirmed]") == 1
    # a non-verified outcome drops a stale marker instead of adding one
    dropped = mark_outcome._annotate_note(twice, None, "PEND")
    assert "[confirmed]" not in dropped, dropped


# ---------------------------------------------------------------------------
# memory.py  (CONSILIUM-MEMORY-001)
# ---------------------------------------------------------------------------

def _memory(*args: str) -> dict:
    import subprocess
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "memory.py"), *args],
        capture_output=True, check=False,
    )
    assert r.returncode == 0, r.stderr.decode()
    return json.loads(r.stdout.decode("utf-8"))


def _memory_fixture(td: str) -> tuple[Path, Path]:
    """(feedback.html, runs/) holding 3 runs and 4 journal rows."""
    runs = Path(td) / "runs"
    runs.mkdir()
    for name, chosen, conf in (("2026-05-01_a", "alpha", 0.5),
                               ("2026-05-02_b", "beta", 0.6),
                               ("2026-05-03_c", "gamma", 0.7)):
        (runs / f"{name}.json").write_text(json.dumps({
            "success_criterion": f"criterion {name}",
            "chosen_approach": chosen, "confidence": conf,
        }), encoding="utf-8")
    fb = Path(td) / "FEEDBACK.html"
    entries = [
        rfh.Entry(date="2026-05-01", context="Rollback plan", chosen="a",
                  outcome="OK", note="seed; [confirmed]"),
        rfh.Entry(date="2026-05-02", context="auth", chosen="do_rollback",
                  outcome="BAD", note="plain"),
        rfh.Entry(date="2026-05-03", context="auth", chosen="c",
                  outcome="OK", note="needs rollback"),
        rfh.Entry(date="2026-05-04", context="cache", chosen="d",
                  outcome="OK", note="unrelated"),
    ]
    fb.write_text(rfh.render(entries, runs_dir=runs), encoding="utf-8")
    return fb, runs


def test_memory_medium_caps_entries_and_reads_run_fields():
    # verifies: CONSILIUM-MEMORY-001#CASE-1
    with tempfile.TemporaryDirectory() as td:
        fb, runs = _memory_fixture(td)
        out = _memory("--tier", "medium", "--n", "2", "--runs-dir", str(runs))
    assert out["tier"] == "medium" and out["total"] == 3, out
    assert [e["chosen"] for e in out["entries"]] == ["gamma", "beta"], out
    assert set(out["entries"][0]) == {
        "run", "date", "success_criterion", "chosen", "confidence"}, out


def test_memory_long_query_is_case_insensitive_and_flags_confirmed():
    # verifies: CONSILIUM-MEMORY-001#CASE-2
    with tempfile.TemporaryDirectory() as td:
        fb, runs = _memory_fixture(td)
        out = _memory("--tier", "long", "--query", "ROLLBACK",
                      "--feedback-file", str(fb))
    # context / chosen / note each matched once; the "cache" row is excluded
    assert [e["chosen"] for e in out["entries"]] == ["a", "do_rollback", "c"]
    assert [e["confirmed"] for e in out["entries"]] == [True, False, False]
    assert out["total"] == 4, out


def test_memory_short_tier_is_a_fixed_stub():
    # verifies: CONSILIUM-MEMORY-001#CASE-3
    out = _memory("--tier", "short")
    assert out["tier"] == "short" and out["entries"] == [], out
    assert "session-local" in out["note"], out


def test_memory_all_tiers_honour_path_overrides():
    # verifies: CONSILIUM-MEMORY-001#CASE-4
    # verifies: CONSILIUM-MEMORY-001#CASE-5
    with tempfile.TemporaryDirectory() as td:
        fb, runs = _memory_fixture(td)
        out = _memory("--tier", "all", "--feedback-file", str(fb),
                      "--runs-dir", str(runs))
    assert set(out) == {"short", "medium", "long"}, sorted(out)
    assert out["medium"]["total"] == 3 and out["long"]["total"] == 4, out


def _run_tests():
    funcs = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_tests())
