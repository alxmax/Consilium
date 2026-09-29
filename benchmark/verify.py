#!/usr/bin/env python3
"""
Verification engine.

Reads `<task>/meta.yaml` from the sibling `Benchmark-scoring/` directory
and runs the appropriate verifier against the model's workspace. Returns
a structured report. The scoring tree lives in a separate sibling repo
(`../Benchmark-scoring/`), outside the Benchmark project root, so the
benchmarked subprocess — which has Bash + filesystem access — cannot reach
it via Glob/Read inside the project tree or via `git log` on this repo.
See `README.md` § "Answer keys (scoring/)" for setup.

Supported `kind`s:
    pytest          — copies a test file into the workspace, runs pytest
    cpp_self_tests  — compiles and runs the model's own C++ test binary
    closed_answer   — extracts ANSWER: <letter> from answer.md, compares to
                      expected_answer.txt
    llm_judge       — sends answer.md + rubric.md to a judge model, parses
                      JSON scores

Invoked automatically by `run_task.py` after each run. Can also be called
standalone to re-score historical runs:

    python verify.py --mode sonnet_bare --task code/01_circuit_breaker
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
# External sibling repo (Doc/Benchmark-scoring), one level above the Consilium
# root that benchmark/ now lives in. Override with BENCHMARK_SCORING_DIR.
SCORING_DIR = Path(
    os.environ.get("BENCHMARK_SCORING_DIR")
    or BASE.parent.parent / "Benchmark-scoring"
)

# Override with BENCHMARK_GXX_PATH (os.pathsep-separated); msys64 = fallback.
EXTRA_PATH_ENTRIES = [
    *[p for p in os.environ.get("BENCHMARK_GXX_PATH", "").split(os.pathsep) if p],
    r"C:\msys64\ucrt64\bin",
    r"C:\msys64\mingw64\bin",
]


def _coerce_scalar(s: str):
    s = s.strip().strip("'").strip('"')
    if s.isdigit():
        return int(s)
    if re.fullmatch(r'-?\d+\.\d+', s):
        return float(s)
    return s


def _load_meta(verify_dir: Path) -> dict | None:
    """Read meta.yaml with a tiny hand-rolled parser (no PyYAML dependency).

    Supports scalars (`key: value`) and inline-flow or block-style lists:
        judge_models: [a, b]
        judge_models:
          - a
          - b
    """
    meta_f = verify_dir / "meta.yaml"
    if not meta_f.exists():
        return None
    out: dict = {}
    current_list_key: str | None = None
    for raw in meta_f.read_text(encoding="utf-8").splitlines():
        body = raw.split("#", 1)[0].rstrip()
        if not body.strip():
            current_list_key = None
            continue
        stripped = body.lstrip()
        # Continuation of a block-style list: `  - item`
        if current_list_key and stripped.startswith("- "):
            out[current_list_key].append(_coerce_scalar(stripped[2:]))
            continue
        current_list_key = None
        if ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        k = k.strip()
        v_str = v.strip()
        if v_str == "":
            # Block-style list follows on the next lines
            out[k] = []
            current_list_key = k
            continue
        if v_str.startswith("[") and v_str.endswith("]"):
            # Inline-flow list
            items = [_coerce_scalar(x) for x in v_str[1:-1].split(",") if x.strip()]
            out[k] = items
            continue
        out[k] = _coerce_scalar(v_str)
    return out


def _augmented_env() -> dict:
    env = os.environ.copy()
    extra = [p for p in EXTRA_PATH_ENTRIES if Path(p).is_dir()]
    if extra:
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    return env


# ── Verifiers ──────────────────────────────────────────

def _verify_pytest(workspace: Path, verify_src: Path, meta: dict) -> dict:
    """Copy test file into workspace, run pytest, parse pass/fail."""
    test_name = meta.get("test_file", "test_solution.py")
    src = verify_src / test_name
    if not src.exists():
        return {
            "ok": False,
            "kind": "pytest",
            "reason": f"hidden test file {test_name} missing in prompts/<task>/verify/",
            "score": 0,
            "max_score": meta.get("max_score", 60),
        }

    ws_verify = workspace / "verify"
    ws_verify.mkdir(exist_ok=True)
    dst = ws_verify / test_name
    shutil.copy(src, dst)

    solution = workspace / "solution.py"
    if not solution.exists():
        return {
            "ok": False,
            "kind": "pytest",
            "reason": "solution.py not found in workspace root — model did not honour the output contract",
            "score": 0,
            "max_score": meta.get("max_score", 60),
        }

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "--tb=short",
             "--no-header", str(dst)],
            cwd=workspace, capture_output=True, text=True, encoding="utf-8",
            env=_augmented_env(),
            timeout=meta.get("timeout_sec", 120),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "kind": "pytest",
            "reason": f"pytest exceeded {meta.get('timeout_sec', 120)}s",
            "score": 0,
            "max_score": meta.get("max_score", 60),
        }

    output = (proc.stdout or "") + "\n--- stderr ---\n" + (proc.stderr or "")
    (ws_verify / "pytest_output.txt").write_text(output, encoding="utf-8")

    passed = len(re.findall(r"PASSED", proc.stdout or ""))
    failed = len(re.findall(r"FAILED", proc.stdout or ""))
    errored = len(re.findall(r"ERROR", proc.stdout or ""))
    total = passed + failed + errored

    if total == 0:
        m = re.search(r"collected (\d+) item", proc.stdout or "")
        if m:
            total = int(m.group(1))

    max_score = meta.get("max_score", 60)
    score = round((passed / total) * max_score) if total else 0
    pct = round(passed / total * 100, 1) if total else 0.0

    return {
        "ok": True,
        "kind": "pytest",
        "passed": passed,
        "failed": failed + errored,
        "total": total,
        "pct": pct,
        "score": score,
        "max_score": max_score,
        "returncode": proc.returncode,
    }


def _verify_cpp_self_tests(workspace: Path, verify_src: Path, meta: dict) -> dict:
    """Compile and run the model's own tests_self.cpp. Exit 0 = pass."""
    src_file = workspace / "tests_self.cpp"
    if not src_file.exists():
        return {
            "ok": False,
            "kind": "cpp_self_tests",
            "reason": "tests_self.cpp not found in workspace root",
            "score": 0,
            "max_score": meta.get("max_score", 60),
        }
    if not (workspace / "solution.hpp").exists() and \
       not (workspace / "solution.cpp").exists():
        return {
            "ok": False,
            "kind": "cpp_self_tests",
            "reason": "neither solution.hpp nor solution.cpp present",
            "score": 0,
            "max_score": meta.get("max_score", 60),
        }

    ws_verify = workspace / "verify"
    ws_verify.mkdir(exist_ok=True)
    exe = workspace / "tests_self.exe"
    build_cmd = meta.get(
        "build_cmd",
        "g++ -std=c++17 -O2 -pthread tests_self.cpp -o tests_self.exe",
    )

    try:
        build = subprocess.run(
            build_cmd, cwd=workspace, shell=True, capture_output=True,
            text=True, encoding="utf-8", env=_augmented_env(),
            timeout=meta.get("timeout_sec", 180),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "kind": "cpp_self_tests",
            "reason": "compile timeout",
            "score": 0, "max_score": meta.get("max_score", 60),
        }

    (ws_verify / "build_output.txt").write_text(
        (build.stdout or "") + "\n--- stderr ---\n" + (build.stderr or ""),
        encoding="utf-8",
    )

    if build.returncode != 0 or not exe.exists():
        return {
            "ok": False, "kind": "cpp_self_tests",
            "reason": f"compile failed (rc={build.returncode})",
            "score": 0, "max_score": meta.get("max_score", 60),
        }

    try:
        run = subprocess.run(
            [str(exe)], cwd=workspace, capture_output=True, text=True,
            encoding="utf-8", env=_augmented_env(),
            timeout=meta.get("timeout_sec", 180),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "kind": "cpp_self_tests",
            "reason": "test binary timeout", "score": 0,
            "max_score": meta.get("max_score", 60),
        }

    (ws_verify / "run_output.txt").write_text(
        (run.stdout or "") + "\n--- stderr ---\n" + (run.stderr or ""),
        encoding="utf-8",
    )

    max_score = meta.get("max_score", 60)
    passed = run.returncode == 0
    return {
        "ok": True, "kind": "cpp_self_tests",
        "passed": int(passed), "failed": int(not passed), "total": 1,
        "pct": 100.0 if passed else 0.0,
        "score": max_score if passed else 0,
        "max_score": max_score,
        "returncode": run.returncode,
    }


def _verify_closed_answer(workspace: Path, verify_src: Path, meta: dict) -> dict:
    answer_md = workspace / "answer.md"
    pattern = meta.get("answer_pattern", r"^\s*ANSWER:\s*([A-Z])\s*$")
    extracted = None
    motivation = None
    if answer_md.exists():
        lines = answer_md.read_text(encoding="utf-8").splitlines()
        answer_line_idx = None
        for i, line in enumerate(lines):
            m = re.match(pattern, line)
            if m:
                try:
                    extracted = m.group(1).upper()
                except IndexError:
                    # answer_pattern matched but defines no capture group —
                    # malformed meta config. Treat as no-extraction rather than
                    # crashing (which would write no report.json at all).
                    break
                answer_line_idx = i
                break
        if answer_line_idx is not None:
            for line in lines[answer_line_idx + 1:]:
                text = line.strip().lstrip("#").strip()
                if text:
                    words = text.split()
                    motivation = " ".join(words[:15])
                    if len(words) > 15:
                        motivation += "…"
                    break

    expected_f = verify_src / meta.get("answer_file", "expected_answer.txt")
    expected = None
    if expected_f.exists():
        for line in expected_f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                expected = line.upper()
                break

    max_score = meta.get("max_score", 100)
    if extracted is None:
        return {
            "ok": False, "kind": "closed_answer",
            "extracted": None, "expected": expected,
            "reason": "no ANSWER: line found in answer.md",
            "score": 0, "max_score": max_score,
        }
    if expected is None:
        return {
            "ok": True, "kind": "closed_answer",
            "extracted": extracted, "expected": None,
            "motivation": motivation,
            "reason": "expected_answer.txt not filled — extraction only",
            "score": None, "max_score": max_score,
        }
    correct = extracted == expected

    # Optional keyword gate (deterministic, no AI). When `require_keywords_any`
    # is set, a correct letter ALSO requires answer.md to contain >=1 of the
    # listed tokens (whole-word, case-insensitive) — so a correct letter paired
    # with an empty or nonsense justification does not score full marks. The token
    # list lives in the task's meta.yaml in the external scoring repo, not here
    # (keeping the answer out of this tracked file). Tasks that don't set the key
    # are unaffected — keyword_ok stays True. (2026-06-23 review: Reviewer 6, Reviewer 4.)
    req_keywords = meta.get("require_keywords_any")
    matched_keyword = None
    if req_keywords:
        haystack = answer_md.read_text(encoding="utf-8").lower() if answer_md.exists() else ""
        for kw in req_keywords:
            if re.search(r"\b" + re.escape(str(kw).lower()) + r"\b", haystack):
                matched_keyword = kw
                break
    keyword_ok = (matched_keyword is not None) if req_keywords else True

    # Optional second check: numeric VALUE: line. Tiered scoring:
    #   letter wrong                                    -> 0
    #   letter right + no VALUE / out of [v_min, v_max] -> 0
    #   letter right + VALUE in [v_min, v_max]          -> range_score
    #   letter right + VALUE in [exact_min, exact_max]  -> max_score
    v_pat   = meta.get("value_pattern")
    v_min   = meta.get("value_min")
    v_max   = meta.get("value_max")
    v_e_min = meta.get("value_exact_min")
    v_e_max = meta.get("value_exact_max")
    range_score = meta.get("range_score", max_score - 1)

    value_check_enabled = bool(v_pat) and v_min is not None and v_max is not None

    if value_check_enabled:
        assert v_min is not None and v_max is not None  # narrow for type-checker
        value_extracted = None
        if answer_md.exists():
            for line in answer_md.read_text(encoding="utf-8").splitlines():
                m = re.match(str(v_pat), line)
                if m:
                    try:
                        value_extracted = float(m.group(1))
                    except (ValueError, IndexError):
                        # ValueError: group not numeric. IndexError: value_pattern
                        # matched but defines no capture group (malformed meta).
                        value_extracted = None
                    break

        if not (correct and keyword_ok):
            bucket, score_val = "wrong_letter", 0
        elif value_extracted is None:
            bucket, score_val = "no_value", 0
        elif (v_e_min is not None and v_e_max is not None
              and float(v_e_min) <= value_extracted <= float(v_e_max)):
            bucket, score_val = "exact", max_score
        elif float(v_min) <= value_extracted <= float(v_max):
            bucket, score_val = "in_range", int(range_score)
        else:
            bucket, score_val = "out_of_range", 0

        return {
            "ok": True, "kind": "closed_answer",
            "extracted": extracted, "expected": expected,
            "motivation": motivation,
            "correct": correct,
            "value_extracted": value_extracted,
            "value_range": [v_min, v_max],
            "value_exact_range": [v_e_min, v_e_max],
            "value_bucket": bucket,
            "score": score_val, "max_score": max_score,
        }

    passed = correct and keyword_ok
    return {
        "ok": True, "kind": "closed_answer",
        "extracted": extracted, "expected": expected,
        "motivation": motivation,
        "correct": correct,
        "keyword_required": bool(req_keywords),
        "keyword_matched": matched_keyword,
        "score": max_score if passed else 0,
        "max_score": max_score,
    }


def _invoke_one_judge(judge_prompt: str, model: str) -> dict:
    """Run one judge model on the given prompt. Returns
    {ok, model, scores, summary, total, raw_stdout, reason?}."""
    claude_bin = shutil.which("claude") or "claude"
    # Pass the prompt via stdin, not argv. On Windows `claude` resolves to
    # claude.cmd (npm shim), and multi-line argv arguments routed through
    # cmd.exe get truncated at the first newline.
    cmd = [
        claude_bin, "-p",
        "--model", model,
        "--effort", "low",
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--max-budget-usd", "1.0",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=BASE, capture_output=True, text=True,
            encoding="utf-8", env=_augmented_env(), timeout=300,
            input=judge_prompt,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "model": model, "reason": "judge timeout (>5min)",
                "raw_stdout": ""}
    except FileNotFoundError:
        return {"ok": False, "model": model, "reason": "claude CLI not found",
                "raw_stdout": ""}

    raw_stdout = proc.stdout or ""
    try:
        outer = json.loads(raw_stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "model": model, "reason": "judge stdout not valid JSON",
                "raw_stdout": raw_stdout}

    text = outer.get("result", "")
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {"ok": False, "model": model, "reason": "no JSON block in judge response",
                "raw_stdout": raw_stdout}
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"ok": False, "model": model, "reason": "judge JSON block did not parse",
                "raw_stdout": raw_stdout}

    scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else None
    total = parsed.get("total")
    if total is None and scores:
        total = sum(v for v in scores.values() if isinstance(v, (int, float)))
    total = float(total or 0)
    return {
        "ok": True, "model": model,
        "scores": scores, "summary": parsed.get("summary"),
        "total": total, "raw_stdout": raw_stdout,
    }


def _median(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _verify_llm_judge(workspace: Path, verify_src: Path, meta: dict) -> dict:
    answer_f = workspace / meta.get("answer_file", "answer.md")
    rubric_f = verify_src / meta.get("rubric_file", "rubric.md")
    max_score = meta.get("max_score", 100)

    if not answer_f.exists():
        return {
            "ok": False, "kind": "llm_judge",
            "reason": f"{answer_f.name} not found in workspace",
            "score": 0, "max_score": max_score,
        }
    if not rubric_f.exists():
        return {
            "ok": False, "kind": "llm_judge",
            "reason": "rubric.md missing in prompts/<task>/verify/",
            "score": 0, "max_score": max_score,
        }

    answer = answer_f.read_text(encoding="utf-8")
    rubric = rubric_f.read_text(encoding="utf-8")
    judge_prompt = (
        f"{rubric}\n\n"
        f"---\n\n"
        f"# Candidate answer to grade\n\n{answer}"
    )

    # Resolve judge model list: `judge_models: [...]` takes priority over
    # `judge_model:` for backward compat with single-judge configs.
    models = meta.get("judge_models")
    if not models:
        models = [meta.get("judge_model", "claude-sonnet-5-5")]

    ws_verify = workspace / "verify"
    ws_verify.mkdir(exist_ok=True)

    judges = []
    for model in models:
        result = _invoke_one_judge(judge_prompt, model)
        judges.append(result)

    # Persist all judge raw outputs for debug. Single judge keeps the legacy
    # filename; multi-judge appends "_<model>.json".
    if len(judges) == 1:
        (ws_verify / "judge_raw.json").write_text(
            judges[0].get("raw_stdout", ""), encoding="utf-8")
    else:
        for j in judges:
            slug = re.sub(r"[^a-z0-9]+", "_", j["model"].lower()).strip("_")
            (ws_verify / f"judge_raw_{slug}.json").write_text(
                j.get("raw_stdout", ""), encoding="utf-8")

    # If a single judge fails, propagate its reason. With multiple judges,
    # we proceed as long as at least one parsed successfully.
    ok_judges = [j for j in judges if j.get("ok")]
    if not ok_judges:
        return {
            "ok": False, "kind": "llm_judge",
            "reason": judges[0].get("reason", "all judges failed"),
            "score": 0, "max_score": max_score,
            "judges": [{k: v for k, v in j.items() if k != "raw_stdout"}
                       for j in judges],
        }

    # Aggregate: per-criterion median across successful judges; total = sum
    # of medians. Falls back gracefully if scores dicts have different keys.
    all_keys = set()
    for j in ok_judges:
        if j.get("scores"):
            all_keys.update(j["scores"].keys())

    merged_scores = {}
    for k in sorted(all_keys):
        vals = [j["scores"][k] for j in ok_judges
                if j.get("scores") and k in j["scores"]
                and isinstance(j["scores"][k], (int, float))]
        if vals:
            merged_scores[k] = round(_median(vals), 1)

    if merged_scores:
        total = sum(merged_scores.values())
    else:
        total = _median([j["total"] for j in ok_judges])
    total = int(round(total))

    # Summary: join all judge summaries with their model name.
    summary_parts = []
    for j in ok_judges:
        if j.get("summary"):
            fam = next((f for f in ("haiku", "sonnet", "opus")
                        if f in j["model"].lower()), j["model"])
            summary_parts.append(f"[{fam}] {j['summary']}")
    summary = " ┃ ".join(summary_parts) if summary_parts else None

    return {
        "ok": True, "kind": "llm_judge",
        "scores": merged_scores or None,
        "summary": summary,
        "score": total, "max_score": max_score,
        "judges": [{k: v for k, v in j.items() if k != "raw_stdout"}
                   for j in judges],
    }


VERIFIERS = {
    "pytest":         _verify_pytest,
    "cpp_self_tests": _verify_cpp_self_tests,
    "closed_answer":  _verify_closed_answer,
    "llm_judge":      _verify_llm_judge,
}


# ── Public API ─────────────────────────────────────────

def run_verification(workspace: Path, task: str) -> dict | None:
    """
    Returns a report dict, or None if no scoring folder exists for this task.
    Writes `<workspace>/verify/report.json` as a side-effect.
    """
    verify_src = SCORING_DIR / task
    if not verify_src.is_dir():
        return None

    meta = _load_meta(verify_src)
    if not meta:
        return {"ok": False, "reason": "meta.yaml missing or empty"}

    kind = str(meta.get("kind") or "")
    verifier = VERIFIERS.get(kind)
    if not verifier:
        return {"ok": False, "reason": f"unknown verifier kind: {kind!r}"}

    report = verifier(workspace, verify_src, meta)

    ws_verify = workspace / "verify"
    ws_verify.mkdir(exist_ok=True)
    (ws_verify / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return report


def format_report_md(report: dict) -> str:
    """Render the verification report as a Markdown section for RESULT.md."""
    if not report:
        return ""
    kind = report.get("kind", "?")
    head = "## Verification (automated)\n\n"
    if not report.get("ok"):
        return head + f"- **Status:** FAILED ({kind})\n- **Reason:** {report.get('reason', '?')}\n- **Score:** {report.get('score', 0)} / {report.get('max_score', '?')}\n"

    if kind == "pytest":
        return head + (
            f"- **Kind:** pytest\n"
            f"- **Passed:** {report['passed']} / {report['total']}  ({report['pct']}%)\n"
            f"- **Score:** {report['score']} / {report['max_score']}\n"
        )
    if kind == "cpp_self_tests":
        return head + (
            f"- **Kind:** C++ self-tests\n"
            f"- **Result:** {'PASS' if report['passed'] else 'FAIL'} (rc={report['returncode']})\n"
            f"- **Score:** {report['score']} / {report['max_score']}\n"
        )
    if kind == "closed_answer":
        extracted = report.get("extracted") or "—"
        motivation = report.get("motivation") or "—"
        expected = report.get("expected")
        if expected is None:
            return head + (
                f"- **Kind:** closed answer\n"
                f"- **Model picked:** `{extracted}` — {motivation}\n"
                f"- **Expected:** _not set yet — fill in `expected_answer.txt`_\n"
                f"- **Score:** N/A\n"
            )
        lines = [
            head,
            f"- **Kind:** closed answer\n",
            f"- **Model picked:** `{extracted}` — {motivation}\n",
            f"- **Expected:** `{expected}`\n",
            f"- **Correct:** {'YES' if report.get('correct') else 'NO'}\n",
        ]
        if "value_bucket" in report:
            v = report.get("value_extracted")
            rng = report.get("value_range") or [None, None]
            exact = report.get("value_exact_range") or [None, None]
            bucket = report.get("value_bucket")
            lines.append(
                f"- **VALUE:** `{v}` (exact [{exact[0]}, {exact[1]}], "
                f"range [{rng[0]}, {rng[1]}]) — bucket: `{bucket}`\n"
            )
        lines.append(
            f"- **Score:** {report['score']} / {report['max_score']}\n"
        )
        return "".join(lines)
    if kind == "llm_judge":
        scores = report.get("scores") or {}
        rows = "\n".join(f"  - {k}: {v}" for k, v in scores.items())
        return head + (
            f"- **Kind:** LLM judge\n"
            f"- **Total:** {report['score']} / {report['max_score']}\n"
            f"- **Breakdown:**\n{rows}\n"
            f"- **Summary:** {report.get('summary', '')}\n"
        )
    return head + f"- **Kind:** {kind}\n- **Score:** {report.get('score', 0)} / {report.get('max_score', '?')}\n"


# ── CLI ────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True)
    ap.add_argument("--task", required=True,
                    help="e.g. code/01_circuit_breaker or reasoning/01_transport_choice")
    args = ap.parse_args()

    task = args.task.replace("\\", "/")
    workspace = BASE / "workspace" / args.mode / task

    if not workspace.exists():
        print(f"ERROR: workspace not found: {workspace}")
        sys.exit(1)

    # If deliverables are in rep_1/ (run_task.py --rep 1 was used) rather
    # than the root, verify against the rep subdirectory.
    _root_has_files = any(workspace.glob("*.cpp")) or any(workspace.glob("*.py")) \
                      or any(workspace.glob("answer.md"))
    if not _root_has_files:
        for sub in sorted(workspace.iterdir()):
            if sub.is_dir() and sub.name.startswith("rep_"):
                if any(sub.glob("*.cpp")) or any(sub.glob("*.py")) \
                        or any(sub.glob("answer.md")):
                    workspace = sub
                    break

    report = run_verification(workspace, task)
    if report is None:
        print(f"No verify/ folder for {task} — nothing to do.")
        return

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport written: {workspace / 'verify' / 'report.json'}")


if __name__ == "__main__":
    main()
