#!/usr/bin/env python3
"""run-consilium driver — build / launch / drive Consilium's runnable surface.

Consilium has no single "app". Its deterministic, drivable surface is:
  - three stdlib-only smoke-test suites,
  - the doc-drift gate,
  - the voice -> report pipeline (aggregator -> confidence,
    build_report -> validate_report),
  - a static React architecture explainer (docs/architecture.html) you can
    screenshot.

This driver exercises all of it without an LLM. Stdlib-only, like the rest
of the repo.

Usage (run from the repo root; paths below are relative to it):
  python .claude/skills/run-consilium/driver.py smoke
      # tests + drift + pipeline (default)
  python .claude/skills/run-consilium/driver.py pipeline
      # voice->report pipeline demo, prints each stage
  python .claude/skills/run-consilium/driver.py shot [OUT.png]
      # screenshot docs/architecture.html via headless Chrome/Edge

Exit 0 iff every step it ran succeeded. On Windows, all child Pythons run
with -X utf8.
"""
# implements: SKILL-RUN-CONSILIUM-001
import json
import os
import subprocess
import sys
from pathlib import Path

# driver.py lives at <repo>/.claude/skills/run-consilium/driver.py
REPO = Path(__file__).resolve().parents[3]
PY = [sys.executable, "-X", "utf8"]
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
       # reqmap gate's map-freshness check needs the public-repo override
       # (memory: omitting it fails CI)
       "REQMAP_REPO": os.environ.get("REQMAP_REPO", "alxmax/Consilium")}

# Baseline of known-failing run_evals scenarios treated as pre-existing (not a
# regression): smoke() exits non-zero only when failures exceed it. Was 6 —
# the validate_report fixtures missing the `pipeline_executed` field required
# since 7176f11; fixed 2026-05-29 (fix/eval-pipeline-executed-drift), so the
# suite is green.
BASELINE_EVAL_FAILURES = 0

# Known headless-capable browsers on Windows (no chromium-cli here).
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def run(label, argv, stdin_text=None):
    """Run a child process from REPO; print a PASS/FAIL line + tail.
    Return CompletedProcess."""
    proc = subprocess.run(
        argv, cwd=REPO, env=ENV, input=stdin_text,
        capture_output=True, text=True, encoding="utf-8",
    )
    ok = proc.returncode == 0
    print(f"[{'PASS' if ok else 'FAIL'}] {label}  (exit {proc.returncode})")
    if not ok:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-12:]
        for line in tail:
            print("    " + line)
    return proc


def eval_failures(proc):
    """Parse run_evals.py's '<n> passed, <m> failed' summary (it writes to
    stderr); -1 if not found."""
    for line in reversed(
        ((proc.stdout or "") + "\n" + (proc.stderr or "")).splitlines()
    ):
        if "passed," in line and "failed" in line:
            try:
                return int(line.split("passed,")[1].split("failed")[0].strip())
            except (ValueError, IndexError):
                return -1
    return -1


def script(rel):
    # Dev tools and tests live in scripts/; the runtime scripts ship in the
    # plugin folder consilium/scripts/.
    dev = REPO / "scripts" / rel
    return PY + [str(dev if dev.exists() else REPO / "consilium" / "scripts" / rel)]


# All scripts/test_*.py unit suites — kept in lockstep with
# .github/workflows/ci.yml.
TEST_SUITES = (
    "test_round2.py",
    "test_feedback_html.py",
    "test_lens_bias.py",
    "test_implement_pipeline.py",
    "test_validate_implement_output.py",
    "test_probe_change.py",
    "test_version.py",
    "test_build_report.py",
    "test_confidence.py",
    "test_priors.py",
    "test_log_feedback.py",
    "test_strip_context.py",
    "test_utils.py",
    "test_scope_gate.py",
    "test_consent_gate.py",
    "test_implement_mode.py",
    "test_vote_degeneracy.py",
    "test_trias_model_schema.py",
    "test_skeptic.py",
    "test_trias_skeptic_lever.py",
    "test_confidence_calibration.py",
    "test_public_leak.py",
    "test_render_impl_preview.py",
    "test_check_versions.py",
    "test_check_doc_drift.py",
    "test_plugin_folder.py",
    "test_changelog_notes.py",
)


def _eval_gate():
    """Run run_evals.py; return 1 if it regressed past the baseline."""
    # run_evals: informational. Only count it as a failure if it regressed
    # past baseline.
    ev = run("run_evals.py (regression scenarios)", script("run_evals.py"))
    failed = eval_failures(ev)
    if failed > BASELINE_EVAL_FAILURES or failed < 0:
        print(f"    -> {failed} eval failures > baseline "
              f"{BASELINE_EVAL_FAILURES}: likely YOUR regression")
        return 1
    if failed:
        print(f"    -> {failed} known eval failures "
              f"(baseline {BASELINE_EVAL_FAILURES}) - pre-existing drift, "
              f"ignored")
    return 0


def _pipeline_tail():
    """Bundle -> canonical report -> Constitution gate; return failures."""
    # Pipeline tail: a full bundle -> canonical report -> Constitution gate.
    bundle = (REPO / "bundle_smoke_tests.json").read_text(encoding="utf-8")
    report = subprocess.run(
        script("build_report.py"), cwd=REPO, env=ENV, input=bundle,
        capture_output=True, text=True, encoding="utf-8",
    )
    if report.returncode != 0:
        print(f"[FAIL] build_report.py  (exit {report.returncode})")
        return 1
    return run(
        "build_report.py | validate_report.py",
        script("validate_report.py"), stdin_text=report.stdout
    ).returncode != 0


def smoke():
    """Run the deterministic suites + drift gate + the pipeline.

    Exit 0 means: every should-be-green check passed AND run_evals regressed
    nothing beyond BASELINE_EVAL_FAILURES (the documented pre-existing drift).
    """
    failures = 0

    for suite in TEST_SUITES:
        failures += run(suite, script(suite)).returncode != 0
    failures += run(
        "check_doc_drift.py", script("check_doc_drift.py")
    ).returncode != 0
    # CI parity: the three blocking ci.yml gates that are not test suites.
    # Without them a local "OK - all green" did not predict a green CI
    # (audit 2026-07-02; the reqmap steps are the recurring red-CI cause
    # after requirement edits).
    failures += run(
        "check_public_leak.py", script("check_public_leak.py")
    ).returncode != 0
    failures += run(
        "reqmap gate --strict", script("reqmap.py") + ["gate", "--strict"]
    ).returncode != 0
    failures += run("architecture build --check",
                    PY + [str(REPO / "docs" / "architecture" / "build.py"),
                          "--check"]).returncode != 0

    failures += _eval_gate()

    failures += _pipeline_tail()

    print(
        "\n"
        f"{'OK - all green' if failures == 0 else f'{failures} step(s) FAILED'}"
    )
    return 1 if failures else 0


def pipeline():
    """Demo the deterministic voice->report pipeline, printing each
    stage's JSON."""
    cands = {"candidates": [
        {"id": "a",
         "scores": {"generator": 0.9, "control": 0.9, "conservator": 0.2}},
        {"id": "b",
         "scores": {"generator": 0.5, "control": 0.5, "conservator": 0.5}},
    ]}
    print("== aggregator (--scheme conservative_override) ==")
    agg = subprocess.run(
        script("aggregator.py") + ["--scheme", "conservative_override"],
        cwd=REPO, env=ENV, input=json.dumps(cands),
        capture_output=True, text=True, encoding="utf-8",
    )
    print(agg.stdout.strip())
    chosen = json.loads(agg.stdout).get("chosen", "a")

    print("\n== confidence ==")
    conf = subprocess.run(
        script("confidence.py"), cwd=REPO, env=ENV,
        input=json.dumps({**cands, "chosen": chosen}),
        capture_output=True, text=True, encoding="utf-8",
    )
    print(conf.stdout.strip())

    print(
        "\n== build_report.py | validate_report.py (bundle_smoke_tests.json) =="
    )
    bundle = (REPO / "bundle_smoke_tests.json").read_text(encoding="utf-8")
    rep = subprocess.run(script("build_report.py"), cwd=REPO, env=ENV,
                         input=bundle,
                         capture_output=True, text=True, encoding="utf-8")
    val = run(
        "validate_report.py", script("validate_report.py"),
        stdin_text=rep.stdout
    )
    return 1 if (
        agg.returncode or conf.returncode or rep.returncode or val.returncode
    ) else 0


def shot(out=None):
    """Screenshot docs/architecture.html with headless Chrome/Edge. Needs
    internet (React/Babel via CDN)."""
    browser = next((b for b in BROWSERS if Path(b).exists()), None)
    if not browser:
        print("FAIL: no Chrome/Edge found. Checked:\n  "
              + "\n  ".join(BROWSERS))
        return 1
    target = REPO / "docs" / "architecture.html"
    out_path = (Path(out) if out
                else REPO / ".consilium" / "shots" / "architecture.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    file_url = target.resolve().as_uri()
    print(f"browser: {browser}\ntarget:  {file_url}\nout:     {out_path}")
    subprocess.run([
        browser, "--headless=new", "--disable-gpu", "--window-size=1280,1600",
        "--virtual-time-budget=8000",
        f"--screenshot={out_path}", file_url,
    ], capture_output=True, text=True)
    ok = out_path.exists() and out_path.stat().st_size > 0
    print(f"[{'PASS' if ok else 'FAIL'}] screenshot "
          f"({out_path.stat().st_size if ok else 0} bytes)")
    return 0 if ok else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if cmd == "smoke":
        raise SystemExit(smoke())
    if cmd == "pipeline":
        raise SystemExit(pipeline())
    if cmd == "shot":
        raise SystemExit(shot(sys.argv[2] if len(sys.argv) > 2 else None))
    print(__doc__)
    raise SystemExit(2)
