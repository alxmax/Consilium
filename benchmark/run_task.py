#!/usr/bin/env python3
"""
Benchmark runner.

Spawns `claude -p` headless with the configured model + effort, parses the
JSON output (cost / duration / tokens), writes RESULT.md. Reports budget /
time-limit / max-turn / timeout exhaustion explicitly. Hard wall-clock cap:
15 min per run (RUN_TIMEOUT_SEC), aligned with the task prompt's 15 min
API-duration limit (raised from 10 min — heavy consilium/trias deliberations
were brushing the old cap). The wall-clock kill is the harness guardrail.

Examples
--------
  python run_task.py --mode sonnet_bare --task code/01_circuit_breaker
  python run_task.py --mode consilium_sequential --task code/01_circuit_breaker --budget 5
  python run_task.py --mode superpowers --task code/01_circuit_breaker
  python run_task.py --mode sonnet_bare --task code/01_circuit_breaker --clean   # wipes that workspace first
"""

import argparse
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import verify as verify_engine

# scripts/extract_deliverables.py — harness-level deliverable extraction.
# When the model emits implementation as a fenced code block in chat but
# doesn't call Write, this extracts each declared deliverable from
# claude_raw.json and writes it to the workspace (idempotent — skips if file
# already exists). See scripts/extract_deliverables.py docstring + Consilium
# an internal design audit.
sys.path.insert(0, str(Path(__file__).parent / "scripts"))
import extract_deliverables  # noqa: E402
import audit_behavior  # noqa: E402
from _common import MODES  # noqa: E402  — single source of truth

BASE           = Path(__file__).parent
PROMPTS        = BASE / "prompts"
WORKSPACE      = BASE / "workspace"
# benchmark/ lives inside the Consilium repo, so its parent IS the Consilium root.
CONSILIUM_ROOT = BASE.parent

# Hard wall-clock cap for any single run (default 15 minutes — aligned with the
# 15-min API-duration limit; raised from 10 min so heavy trias/dialectic
# deliberations on the code task aren't killed mid-pipeline). Override per-run
# with the RUN_TIMEOUT_SEC env var (seconds).
RUN_TIMEOUT_SEC = int(os.environ.get("RUN_TIMEOUT_SEC", 15 * 60))

# Toolchains we want available to every run (fair to all modes).
# Override with BENCHMARK_GXX_PATH (os.pathsep-separated); the msys64 paths
# below stay as the fallback when the env var is unset.
EXTRA_PATH_ENTRIES = [
    *[p for p in os.environ.get("BENCHMARK_GXX_PATH", "").split(os.pathsep) if p],
    r"C:\msys64\ucrt64\bin",   # g++ 14.2 (UCRT)
    r"C:\msys64\mingw64\bin",  # fallback
]

MODE_PREFIXES = {
    "consilium_sequential":  "/consilium ",
    "consilium_trias":       "/consilium --mode trias ",
    "consilium_dialectic":   "/consilium --mode dialectic ",
    "superpowers":           "",
    "sonnet_bare":           "",
}

# CONSILIUM_SUFFIX removed (2026-05-18) — Step 6.5 in Consilium SKILL.md now
# enforces deliverable writes for any prompt that declares files (benchmark or
# not), with verify-then-emit gate. Keeping the suffix here would duplicate the
# contract across two sources of truth.

# Per-mode model pin. Modes whose name implies a specific model lock to it,
# regardless of the --model flag default. Pass --model explicitly to override.
MODE_MODELS = {
    "sonnet_bare": "claude-sonnet-5-5",
}

# Per-mode budget overrides (USD). Default budget ($5) is uniform across modes
# now; leave this dict empty unless a specific mode genuinely needs more.
MODE_BUDGETS = {}

# ── Helpers ────────────────────────────────────────────

def parse_num(s):
    s = str(s).replace(",", "").strip()
    if s.endswith("k"): return float(s[:-1]) * 1_000
    if s.endswith("m"): return float(s[:-1]) * 1_000_000
    return float(s)

def delta(est, actual):
    try:
        e, a = parse_num(est), parse_num(actual)
        return f"{((a - e) / e * 100):+.0f}%" if e else "N/A"
    except Exception:
        return "N/A"

def cal_score(d):
    try:
        pct = abs(float(d.replace("%", "").replace("+", "")))
        if pct <= 20:  return 10
        if pct <= 50:  return 7
        if pct <= 200: return 3
        return 0
    except Exception:
        return 0

def api_mins(s):
    if not s: return 0
    m   = re.search(r"(\d+)m", s)
    sec = re.search(r"([\d.]+)s", s)
    return (int(m.group(1)) if m else 0) + (float(sec.group(1)) / 60 if sec else 0)

def pass_fail(dur, limit):
    if not dur: return "?"
    return "PASS" if api_mins(dur) <= limit else f"FAIL  (>{limit} min)"

def time_bonus(dur, threshold):
    if not dur: return "?"
    return f"+5  (under {threshold} min)" if api_mins(dur) <= threshold else "+0"

def autonomy_penalty(q):
    return "0" if q == 0 else "-5" if q <= 3 else "-15" if q <= 10 else "-25"

def fmt_duration_ms(ms):
    if not ms: return "—"
    s = ms / 1000
    m, sec = divmod(s, 60)
    return f"{int(m)}m {sec:.1f}s" if m else f"{sec:.1f}s"

def parse_self_estimate(text):
    """Extract the model's self-estimate from its response.

    Looks for a `## Self-estimate` (or legacy `## Token Usage`) trailer and
    pulls:
      - lines:      estimated deliverable line count (the calibration metric)
      - input:      legacy input-tokens estimate (kept for back-compat display)
      - output:     legacy output-tokens estimate (kept for back-compat display)
      - reasoning:  YES / NO + optional percentage
    """
    est = {"lines": "N/A", "input": "N/A", "output": "N/A", "reasoning": "N/A"}
    for line in text.splitlines():
        ll = line.lower()
        # Primary calibration metric: lines in deliverables.
        # Match only explicit phrasings so casual mentions of "first line",
        # "command line" etc. don't capture stray numbers.
        m = re.search(
            r"(?:estimated\s+(?:deliverable\s+)?lines?"
            r"|deliverable\s+lines?"
            r"|lines?\s+in\s+deliverables?)"
            r"[^:]*:?\s*~?([\d,]+k?)",
            ll,
        )
        if m and est["lines"] == "N/A":
            est["lines"] = m.group(1)
        m = re.search(r"input tokens?[^:]*:?\s*~?([\d,]+k?)", ll)
        if m and est["input"] == "N/A":
            est["input"] = m.group(1)
        m = re.search(r"output tokens?[^:]*:?\s*~?([\d,]+k?)", ll)
        if m and est["output"] == "N/A":
            est["output"] = m.group(1)
        m = re.search(r"reasoning used?[^:]*:?\s*(yes|no)[^\n]*?([\d]+\s*%)?", ll)
        if m and est["reasoning"] == "N/A":
            est["reasoning"] = m.group(1).upper()
            if m.group(2):
                est["reasoning"] += f" ({m.group(2).strip()})"
    return est

def count_questions(text):
    in_code = False
    count = 0
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        elif not in_code and line.strip().endswith("?"):
            count += 1
    return count

# Skill prints run-paths as .consilium/runs/<f>.json; the optional prefix
# keeps the bare runs/<f>.json form matching too (legacy / canonicalized).
_RUN_PATH_RE = re.compile(r"(?:\.consilium/)?\bruns/[\w\-.]+\.json\b")


def _consilium_engaged(workspace: Path, raw_json: dict | None) -> bool:
    """Deterministically detect, from the session transcript (the ground truth of
    what actually executed — not the skill's prose output), whether the consilium
    deliberation was engaged.

    Relying on the JSONL transcript rather than on the skill printing a
    `.consilium/runs/` path makes detection robust to how the model interprets
    SKILL.md (Python > prose). Headless runs activate the skill via the
    `/consilium` slash command, which appears as a `<command-name>` in a user
    message — NOT as a `Skill` tool_use — so the earlier tool_use-only proxy
    missed every slash-command activation (2026-06-20 audit).

    Returns True if any of these hard signals is present:
      - a user message carrying a `<command-name>` that names consilium
        (the /consilium slash command fired → the skill activated);
      - a `Skill` tool_use naming consilium;
      - an `Agent`/`Task` dispatch of a consilium sub-agent.
    """
    if not raw_json:
        return False
    session_id = raw_json.get("session_id")
    if not session_id:
        return False
    try:
        from check_trias_parallelism import _find_jsonl
    except Exception:
        return False
    jsonl = _find_jsonl(workspace, session_id)
    if jsonl is None:
        return False
    try:
        with jsonl.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = ev.get("message", {})
                if not isinstance(msg, dict):
                    continue
                content = msg.get("content")
                if msg.get("role") == "user":
                    text = (content if isinstance(content, str)
                            else " ".join(b.get("text", "") for b in (content or [])
                                           if isinstance(b, dict)))
                    low = text.lower()
                    if "<command-name>" in low and "consilium" in low:
                        return True
                elif msg.get("role") == "assistant" and isinstance(content, list):
                    for b in content:
                        if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                            continue
                        if b.get("name") not in ("Skill", "Agent", "Task"):
                            continue
                        inp = b.get("input", {})
                        val = (" ".join(str(v) for v in inp.values())
                               if isinstance(inp, dict) else str(inp))
                        if "consilium" in val.lower():
                            return True
    except OSError:
        return False
    return False


def detect_pipeline_execution(mode: str, response: str, workspace: Path,
                              raw_json: dict | None = None) -> None:
    """Record whether a consilium_* run actually executed the deliberation pipeline.

    Authoritative signal is the JSONL transcript (`_consilium_engaged`): the
    `/consilium` slash command firing, a Skill tool_use, or a consilium sub-agent
    dispatch. A response-text `.consilium/runs/<file>.json` path (SKILL.md Step 6)
    is kept as a secondary signal. A run that answers directly without engaging
    the skill triggers neither. Non-consilium modes have no pipeline → status null.

    Writes pipeline_audit.json so analyze.py can mark the cell. Without this, a
    sequential run that answered directly is indistinguishable from bare Sonnet
    in the report (the gap found in the 2026-05-26 audit).
    """
    if not mode.startswith("consilium_"):
        return
    run_paths = _RUN_PATH_RE.findall(response or "")
    # Two complementary signals.
    # `engaged` (transcript): the consilium skill actually fired — /consilium slash
    # command, a Skill tool_use, or a sub-agent dispatch. Authoritative for "did the
    # skill run at all", and catches runs that engaged without leaving a runs/ path.
    engaged = _consilium_engaged(workspace, raw_json)
    # `pipeline_executed`/`pipeline_mode` (report): read the actual run report(s) to
    # tell a FULL pipeline from a Conservator scale_down short-circuit (skip Control).
    # Both write a report, so engagement alone can't tell them apart — surfacing
    # pipeline_executed + telemetry.mode keeps the measured object honest
    # (2026-06-23 review condition).
    pipeline_executed = None
    pipeline_mode = None
    for rel in run_paths:
        run_file = CONSILIUM_ROOT / rel
        if not run_file.exists():
            continue
        try:
            run_data = json.loads(run_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pipeline_executed = bool(run_data.get("pipeline_executed"))
        pipeline_mode = (run_data.get("telemetry") or {}).get("mode")
        break
    (workspace / "pipeline_audit.json").write_text(
        json.dumps({
            "report_detected": engaged or bool(run_paths),
            "run_paths": run_paths,
            "skill_engaged": engaged,
            "pipeline_executed": pipeline_executed,
            "pipeline_mode": pipeline_mode,
            "signal": "transcript: /consilium command | Skill tool_use | sub-agent dispatch; OR runs/ path in response; report pipeline_executed/telemetry.mode",
        }, indent=2),
        encoding="utf-8",
    )


def fix_pend_headless(response: str) -> None:
    """Convert PEND entries created by this benchmark run to PEND_HEADLESS."""
    fix_script = CONSILIUM_ROOT / "scripts" / "fix_benchmark_pendings.py"
    if not fix_script.exists():
        return
    run_paths = _RUN_PATH_RE.findall(response)
    if not run_paths:
        return
    abs_paths = [str(CONSILIUM_ROOT / p) for p in run_paths]
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(fix_script), "--run-paths"] + abs_paths,
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.stdout.strip():
        print(f"  PEND -> PEND_HEADLESS: {result.stdout.strip()}")
    if result.returncode != 0 and result.stderr.strip():
        print(f"  ! fix_benchmark_pendings: {result.stderr.strip()}")


# ── claude -p invocation ───────────────────────────────

EXHAUSTION_MSG = {
    "error_max_budget_usd": "BUDGET EXHAUSTED",
    "error_max_turns":      "MAX TURNS reached",
    "error_max_duration":   "MAX DURATION reached",
    "timeout":              f"TIMEOUT reached ({RUN_TIMEOUT_SEC // 60} min wall-clock)",
}

# Scoring stash mechanism — see SCORING_STASH_NOTES below for the why.
#
# The harness needs `bypassPermissions` to keep all task types working
# (Read on workspace, Bash for compile/test, etc.). Under bypassPermissions,
# --disallowedTools is silently ignored (probed 2026-05-19, sonnet 4.6),
# so deny patterns are not a viable sandbox.
#
# Instead: before spawning the subprocess, we physically move the sibling
# Benchmark-scoring/ directory to a temp path with a random name that
# contains neither "scoring" nor "Benchmark". After the subprocess exits,
# we move it back. During the run, no file path the model can derive
# leads to the scoring tree.
SCORING_DIR = Path(
    os.environ.get("BENCHMARK_SCORING_DIR")
    or BASE.parent.parent / "Benchmark-scoring"
)
WORKSPACE_DIR = Path(__file__).parent / "workspace"
# Two prefixes — opaque on purpose, no "scoring" / "workspace" substring.
SCORING_STASH_PREFIX = ".bms_scoring_"
WORKSPACE_STASH_PREFIX = ".bms_ws_"
STASH_ROOT = Path(tempfile.gettempdir())


def _recover_orphan_stashes():
    """Restore stashes left behind by a crashed previous run.

    Two flavours, restored independently:
      - `.bms_scoring_<hex>`  -> ../Benchmark-scoring/
      - `.bms_ws_<hex>`       -> workspace/ subdirs (multi-file restore
                                  via manifest.json inside the stash)
    Idempotent — safe to call at every invocation.
    """
    # Scoring stash: at most one expected at a time.
    if not SCORING_DIR.exists():
        candidates = sorted(STASH_ROOT.glob(f"{SCORING_STASH_PREFIX}*"))
        if len(candidates) == 1:
            orphan = candidates[0]
            print(f"  Recovering orphan scoring stash: {orphan.name} -> Benchmark-scoring/")
            shutil.move(str(orphan), str(SCORING_DIR))
        elif len(candidates) > 1:
            print(f"  ! Multiple orphan scoring stashes found in {STASH_ROOT}:")
            for c in candidates:
                print(f"      {c}")
            print(f"  ! Manual review needed — move one to {SCORING_DIR} and delete the rest.")

    # Workspace stash: each `.bms_ws_<hex>/manifest.json` lists the moves
    # made by a crashed run. Apply each in reverse, then delete the stash.
    for ws_stash in sorted(STASH_ROOT.glob(f"{WORKSPACE_STASH_PREFIX}*")):
        manifest = ws_stash / "manifest.json"
        if not manifest.exists():
            continue
        try:
            moves = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        print(f"  Recovering orphan workspace stash: {ws_stash.name} ({len(moves)} dirs)")
        for entry in reversed(moves):
            orig = Path(entry["orig"])
            stashed = Path(entry["stashed"])
            if stashed.exists() and not orig.exists():
                orig.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(stashed), str(orig))
        try:
            shutil.rmtree(str(ws_stash), ignore_errors=True)
        except OSError:
            pass


def _rmtree_force(path: str) -> None:
    """Remove a directory tree, clearing read-only bits first (Windows .git objects)."""
    def _on_readonly(func, fpath, _):
        os.chmod(fpath, stat.S_IWRITE)
        func(fpath)
    shutil.rmtree(path, onerror=_on_readonly)


def _move_dir(src: Path, dst: Path) -> None:
    """Move a directory, handling read-only files (Windows git repos)."""
    try:
        os.rename(str(src), str(dst))
    except OSError:
        shutil.copytree(str(src), str(dst))
        _rmtree_force(str(src))


@contextmanager
def stash_scoring_for_run():
    """Move Benchmark-scoring/ to a random temp path for the duration of
    the subprocess. Restored in `finally` to survive crashes inside the
    context. A hard kill (e.g. OS reboot) leaves an orphan that
    `_recover_orphan_stashes()` will restore at next startup."""
    if not SCORING_DIR.exists():
        # Already missing — likely a fresh checkout without the sibling
        # repo cloned yet. Verify.py will report missing scoring later.
        yield
        return
    stash_name = SCORING_STASH_PREFIX + secrets.token_hex(16)
    stash_path = STASH_ROOT / stash_name
    _move_dir(SCORING_DIR, stash_path)
    try:
        yield
    finally:
        if stash_path.exists() and not SCORING_DIR.exists():
            _move_dir(stash_path, SCORING_DIR)


def _windows_safe_move(src: Path, dst: Path, retries: int = 5, base_delay: float = 0.4):
    """`shutil.move` with retry — Windows holds onto file/dir handles for a
    moment after a process closes (browser caching report.html, search
    indexer, the `claude` subprocess flushing logs). One retry is usually
    enough; we try up to `retries` with exponential backoff before raising
    with a clear hint to the user."""
    last_err = None
    for attempt in range(retries):
        try:
            shutil.move(str(src), str(dst))
            return
        except PermissionError as e:
            last_err = e
            # shutil.move falls back to copytree when os.rename is denied,
            # which can partially create dst before hitting a locked file.
            # Clean up the partial destination so the next retry starts fresh.
            if dst.is_dir():
                shutil.rmtree(str(dst), ignore_errors=True)
            time.sleep(base_delay * (2 ** attempt))
        except OSError as e:
            # WinError 32 (sharing violation) also surfaces as OSError
            if getattr(e, "winerror", None) == 32:
                last_err = e
                if dst.is_dir():
                    shutil.rmtree(str(dst), ignore_errors=True)
                time.sleep(base_delay * (2 ** attempt))
            else:
                raise
    raise PermissionError(
        f"Could not move {src} after {retries} retries — a process is holding "
        f"a handle inside this directory. Close any browser tab on report.html, "
        f"any editor on files in this workspace, and re-run.\n"
        f"Underlying error: {last_err}"
    )


@contextmanager
def stash_sibling_workspaces(current_workspace: Path):
    """Hide every workspace/ subdirectory NOT on the path to `current_workspace`.

    Cross-mode contamination is a real leak vector even after the scoring
    stash: when run-all runs every mode sequentially, the LATER modes can
    Glob `workspace/<earlier-mode>/<this-task>/answer.md` and copy the
    answer rather than computing. This context moves every sibling
    `workspace/<mode>/<task>/` (and every alternate task under the
    current mode) to a stash dir for the duration of the subprocess.

    Restoration writes a manifest.json BEFORE moving so that
    `_recover_orphan_stashes()` can roll back a crashed run on next startup.
    """
    if not WORKSPACE_DIR.is_dir() or not current_workspace.is_dir():
        yield
        return

    ws_root_res = WORKSPACE_DIR.resolve()
    cwd_res = current_workspace.resolve()
    if ws_root_res not in cwd_res.parents:
        # current_workspace not under workspace/; nothing to do.
        yield
        return

    # Build the chain of directories from workspace/ down to cwd. These
    # must remain in place; everything else (siblings at every level)
    # gets stashed.
    keep = set()
    p = cwd_res
    while True:
        keep.add(p)
        if p == ws_root_res:
            break
        p = p.parent

    stash = STASH_ROOT / (WORKSPACE_STASH_PREFIX + secrets.token_hex(16))
    stash.mkdir(parents=True)
    moves = []  # list of {orig, stashed} dicts for manifest + restore

    def _restore():
        for entry in reversed(moves):
            orig = Path(entry["orig"])
            target = Path(entry["stashed"])
            if target.exists() and not orig.exists():
                orig.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(target), str(orig))
                except OSError as e:
                    print(f"  ! restore failed for {orig}: {e}")
        try:
            shutil.rmtree(str(stash), ignore_errors=True)
        except OSError:
            pass

    # Wrap the moves loop in try/except so that a failure mid-loop still
    # restores everything that was already moved. Without this, a crash
    # leaves workspaces orphaned in %TEMP%/.bms_ws_<hex>.
    # rep_N siblings of cwd are replicates of THE SAME (mode, task) cell —
    # they contain no scoring secrets and need not be stashed. Excluding
    # them avoids cross-rep filesystem moves (and the shutil.Error path
    # collisions that have crashed dialectic batches in the past).
    cwd_parent_res = cwd_res.parent.resolve() if cwd_res != ws_root_res else None
    try:
        for k in keep:
            if not k.is_dir():
                continue
            for child in list(k.iterdir()):
                if not child.is_dir():
                    continue
                if child.resolve() in keep:
                    continue
                # Skip sibling replicates of the current rep (workspace/<mode>/
                # <task>/rep_<other>/). These are NOT a cross-contamination risk
                # because they belong to the same cell as cwd.
                if (cwd_parent_res is not None
                        and child.parent.resolve() == cwd_parent_res
                        and child.name.startswith("rep_")):
                    continue
                rel = child.resolve().relative_to(ws_root_res)
                target = stash / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                _windows_safe_move(child, target)
                moves.append({
                    "orig": str(child.resolve()),
                    "stashed": str(target.resolve()),
                })
    except Exception:
        _restore()
        raise

    # Manifest enables orphan recovery if Python crashes hard.
    (stash / "manifest.json").write_text(
        json.dumps(moves, indent=2), encoding="utf-8"
    )

    try:
        yield
    finally:
        _restore()


def auto_run(workspace, full_prompt, model, effort, budget):
    """Invoke claude -p; return (response_text, usage_dict, error_info, raw_json).

    The subprocess runs with cwd=workspace and --permission-mode bypassPermissions.
    cwd is NOT a sandbox — the model can read any absolute path. Real
    isolation comes from `stash_scoring_for_run()`, which physically moves
    `Benchmark-scoring/` to a random temp path during the subprocess and
    restores it afterward. The model's own glob patterns (`**/expected_answer*`,
    `**/Benchmark-scoring/**`) match nothing during the run because the
    directory doesn't exist at any predictable path.
    """
    claude_bin = shutil.which("claude") or "claude"
    # Prompt delivery is mode-dependent (see the 2026-06-23 benchmark audit):
    #
    #   * Non-slash modes (sonnet_bare, superpowers) → STDIN. Historically chosen
    #     because passing a multi-line prompt as an argv positional truncated at
    #     the first newline on Windows (2026-05-20 finding). These modes don't
    #     need slash expansion, so stdin is correct and stays.
    #
    #   * Slash-command modes (consilium_*, prompt starts with "/consilium") MUST
    #     pass the prompt as the `-p` ARGUMENT. `claude -p` only expands a slash
    #     command when it is the -p argument at position 0 — a slash command piped
    #     via stdin is treated as literal text and the skill never loads (the run
    #     collapses to bare Sonnet: num_turns=2, no report). Verified empirically
    #     2026-06-23: identical prompt as `-p <arg>` → num_turns=10, skill ran;
    #     via stdin → num_turns=2, no skill. List-form subprocess (no shell)
    #     preserves the multi-line argv intact, so the 2026-05-20 truncation
    #     (which was via the cmd.exe/.cmd shim path) does not apply here.
    via_arg = full_prompt.lstrip().startswith("/")
    base_flags = [
        "--model", model,
        "--effort", effort,
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--max-budget-usd", str(budget),
    ]
    # Beta channel: with BENCHMARK_CONSILIUM_DEV=1, run consilium modes against the
    # LOCAL dev skill (this repo, an installable plugin named "consilium") instead of
    # the marketplace-installed plugin. --plugin-dir takes precedence over the
    # same-named marketplace plugin for that invocation, so unmerged/beta skill
    # changes can be measured in the benchmark before they are released to the
    # published plugin. Only consilium_* modes (via_arg) load the skill.
    if via_arg and os.environ.get("BENCHMARK_CONSILIUM_DEV") == "1":
        base_flags += ["--plugin-dir", str(CONSILIUM_ROOT)]
    if via_arg:
        # Flags FIRST, `-p <prompt>` LAST. A multi-line slash-command prompt
        # placed before the flags corrupts parsing of whatever follows it —
        # --output-format json gets dropped and stdout comes back as prose,
        # breaking metric extraction. Putting the prompt last keeps json intact
        # AND expands the slash command. Verified empirically 2026-06-23.
        cmd = [claude_bin] + base_flags + ["-p", full_prompt]
    else:
        cmd = [claude_bin, "-p"] + base_flags
    print(f"\n  Spawning: claude -p --model {model} --effort {effort} --max-budget-usd {budget}")
    print(f"  Workspace:    {workspace}  (subprocess cwd — model is sandboxed here)")
    print(f"  Budget cap:   ${budget}")
    print(f"  Timeout cap:  {RUN_TIMEOUT_SEC // 60} min (wall-clock)")
    print(f"  Prompt:       {len(full_prompt)} chars via {'-p arg (slash expansion)' if via_arg else 'stdin'}")
    print(f"  This may take several minutes...\n")

    # Augment PATH so the spawned claude (and any tools it shells out to,
    # like g++ for the C++ task) can find the toolchain.
    env = os.environ.copy()
    extra = [p for p in EXTRA_PATH_ENTRIES if Path(p).is_dir()]
    if extra:
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])

    run_started_at = time.time()
    try:
        with stash_scoring_for_run(), stash_sibling_workspaces(workspace):
            proc = subprocess.run(
                cmd, cwd=workspace, capture_output=True, text=True, encoding="utf-8",
                env=env, timeout=RUN_TIMEOUT_SEC,
                input=None if via_arg else full_prompt,
            )
    except FileNotFoundError:
        print("  ERROR: `claude` binary not found on PATH.")
        sys.exit(2)
    except subprocess.TimeoutExpired as e:
        mins = RUN_TIMEOUT_SEC // 60
        print(f"\n  ! TIMEOUT -- run exceeded {mins} min wall-clock; subprocess killed.")
        partial_out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        return (
            partial_out,
            {"model": model, "api_duration": f"{mins}m 0.0s", "wall": f"{mins}m 0.0s"},
            {"error": "timeout", "message": EXHAUSTION_MSG["timeout"]},
            None,
        )

    stdout, stderr = proc.stdout or "", proc.stderr or ""

    if not stdout.strip():
        print(f"  ERROR: empty stdout from claude (returncode={proc.returncode})")
        if stderr:
            print(f"  stderr (first 1000 chars):\n{stderr[:1000]}")
        return "", {"model": model}, {"error": "empty_stdout"}, None

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        print(f"  ERROR: could not parse JSON ({e})")
        print(f"  Raw stdout (first 1500 chars):\n{stdout[:1500]}")
        return stdout, {"model": model}, {"error": "json_parse"}, None

    # ── Error / exhaustion detection ──
    error_info = {}
    subtype    = data.get("subtype", "")
    if data.get("is_error") or subtype not in ("success", ""):
        friendly = EXHAUSTION_MSG.get(subtype, subtype or "unknown")
        error_info = {"error": subtype or "is_error", "message": friendly}
        print(f"\n  ! RUN HALTED -- {friendly}")
        if stderr:
            print(f"  stderr (first 400): {stderr[:400]}")

    # ── Usage extraction ──
    u   = data.get("usage", {}) or {}
    in_tok    = u.get("input_tokens")
    out_tok   = u.get("output_tokens")
    cache_r   = u.get("cache_read_input_tokens")
    cache_w   = u.get("cache_creation_input_tokens")

    # Behavior audit — scan the session transcript for scoring-key access.
    # `run_started_at` filters out historical sessions in the same projects/
    # dir (manual probes, prior runs) so we only inspect this run.
    audit = audit_behavior.audit_workspace_run(workspace, run_started_at)
    (workspace / "behavior_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Behavior:     {audit['summary']}")

    usage = {
        "cost":         f"{data.get('total_cost_usd', 0):.4f}",
        "api_duration": fmt_duration_ms(data.get("duration_api_ms")),
        "wall":         fmt_duration_ms(data.get("duration_ms")),
        "input":        str(in_tok)  if in_tok  is not None else "—",
        "output":       str(out_tok) if out_tok is not None else "—",
        "cache_read":   str(cache_r) if cache_r is not None else "—",
        "cache_write":  str(cache_w) if cache_w is not None else "—",
        "model":        model,
        "num_turns":    str(data.get("num_turns", "—")),
        "lines_added":  str(count_workspace_lines(workspace)),
        "behavior":     audit["verdict"],
        "behavior_summary": audit["summary"],
    }

    response = data.get("result", "") or ""
    return response, usage, error_info, data

def count_workspace_lines(workspace):
    """Crude additive line count of code/text files in workspace."""
    exts = {".cpp", ".hpp", ".h", ".c", ".cc", ".py", ".js", ".ts",
            ".go", ".rs", ".java", ".md", ".txt", ".sh", ".ps1"}
    total = 0
    if not workspace.exists():
        return 0
    for f in workspace.rglob("*"):
        if f.is_file() and f.suffix.lower() in exts:
            try:
                total += sum(1 for _ in f.open("r", encoding="utf-8", errors="ignore"))
            except Exception:
                pass
    return total

def count_deliverable_lines(workspace, declared_files):
    """Sum lines across just the declared deliverable files.

    Used as the actual measurement for the model's self-estimated deliverable
    size — independent of mode-specific overhead like PROCESS.md.
    """
    total = 0
    for fname in declared_files:
        target = workspace / fname
        if not target.exists():
            continue
        try:
            total += sum(1 for _ in target.open("r", encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    return total

# ── Result writer ──────────────────────────────────────

def write_result(workspace, mode, task, usage, self_est, response, questions,
                 error_info=None, raw_json=None, verify_report=None):
    d_out     = delta(self_est["output"], usage.get("output", ""))
    d_lines   = delta(self_est["lines"],  usage.get("deliverable_lines", ""))
    cal       = cal_score(d_lines)
    is_reason = "reasoning" in task
    limit     = 15
    threshold = 5 if is_reason else 10
    err_line  = ""
    if error_info and error_info.get("error"):
        err_line = f"\n> ⚠ **Run halted:** {error_info.get('message', error_info['error'])}\n"

    verify_md = verify_engine.format_report_md(verify_report) if verify_report else ""
    if verify_md:
        verify_md = "\n" + verify_md + "\n---\n"

    md = f"""# RESULT — {task} | {mode}
_Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}_
{err_line}{verify_md}
---

## Timing
| Metric                | Value |
|-----------------------|-------|
| API Duration          | {usage.get("api_duration", "—")} |
| Wall Duration         | {usage.get("wall", "—")} |
| Time limit ({limit}m) | {pass_fail(usage.get("api_duration"), limit)} |
| Model                 | {usage.get("model", "—")} |
| Num turns             | {usage.get("num_turns", "—")} |
| Lines (workspace)     | {usage.get("lines_added", "—")} |
| Behavior audit        | {usage.get("behavior_summary", "—")} |

---

## Self-estimate vs actual
_Calibration metric (Self-Awareness rubric) is **deliverable lines** — concrete and measurable post-run. Token columns are diagnostic only._

| Metric                    | Self-estimated | Actual | Delta |
|---------------------------|----------------|--------|-------|
| Deliverable lines         | {self_est["lines"]} | {usage.get("deliverable_lines", "—")} | {d_lines} |
| Cache read tokens         | — | {usage.get("cache_read", "—")} | — |
| Input tokens (final turn) | {self_est["input"]} | {usage.get("input", "—")} | — |
| Output tokens (session)   | {self_est["output"]} | {usage.get("output", "—")} | {d_out} |
| Cache write               | — | {usage.get("cache_write", "—")} | — |
| Cost                      | — | ${usage.get("cost", "—")} | — |
| Reasoning                 | {self_est["reasoning"]} | — | — |

---

## Autonomy
| Clarifying questions (detected) | {questions} |
|---------------------------------|-------------|
| Autonomy penalty                | {autonomy_penalty(questions)} |

---

## Scoring
"""
    if not is_reason:
        md += f"""
### Code Implementation — 60 pts
| Criterion    | Score | Notes |
|--------------|-------|-------|
| Correctness  |  /20  |       |
| Code Quality |  /15  |       |
| Completeness |  /15  |       |
| Edge Cases   |  /10  |       |
| **Subtotal** |  /60  |       |

### Reasoning — 40 pts
| Criterion                          | Score | Notes |
|------------------------------------|-------|-------|
| Problem Analysis Depth             |  /15  |       |
| Decision Justification             |  /15  |       |
| Self-Awareness (cal: {cal}/10)     |  /10  | delta lines: {d_lines} |
| **Subtotal**                       |  /40  |       |
"""
    else:
        md += f"""
### Reasoning — 100 pts
| Criterion                          | Score | Notes |
|------------------------------------|-------|-------|
| Paradox / problem identified       |  /25  |       |
| Hypothesis quality                 |  /25  |       |
| Reasoning depth                    |  /25  |       |
| Self-awareness (cal: {cal}/10)     |  /25  | delta lines: {d_lines} |
| **Subtotal**                       | /100  |       |
"""

    md += f"""
### Adjustments
| Time bonus       | {time_bonus(usage.get("api_duration"), threshold)} |
|------------------|---|
| Autonomy penalty | {autonomy_penalty(questions)} |

### FINAL SCORE: /100

---

## Files delivered
- [ ]

---

## Self-assessment (from model)
_(see RESULT_response.md)_
"""
    (workspace / "RESULT.md").write_text(md, encoding="utf-8")
    (workspace / "RESULT_response.md").write_text(
        f"# Response — {task} | {mode}\n\n{response}", encoding="utf-8")

    if raw_json is not None:
        (workspace / "claude_raw.json").write_text(
            json.dumps(raw_json, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  Written: {workspace / 'RESULT.md'}")
    print(f"  Written: {workspace / 'RESULT_response.md'}")
    if raw_json is not None:
        print(f"  Written: {workspace / 'claude_raw.json'}")

# ── Main ───────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode",   required=True, choices=MODES)
    ap.add_argument("--task",   required=True,
                    help="e.g. code/01_circuit_breaker, reasoning/01_transport_choice, reasoning/02_rule_of_three")
    ap.add_argument("--clean",  action="store_true",
                    help="Wipe this task's workspace before running")
    ap.add_argument("--model",  default="claude-sonnet-5-5",
                    help="Model id or alias (default: claude-sonnet-5-5)")
    ap.add_argument("--effort", default="high",
                    choices=["low", "medium", "high", "xhigh", "max"],
                    help="Effort level (default: high)")
    ap.add_argument("--budget", type=float, default=5.0,
                    help="--max-budget-usd cap in USD (default: 5.0)")
    ap.add_argument("--no-verify", action="store_true",
                    help="Skip automatic verification step after the run")
    ap.add_argument("--rep", type=int, default=None, metavar="N",
                    help="Replicate index. Writes to workspace/<mode>/<task>/rep_<N>/ "
                         "instead of workspace/<mode>/<task>/. Use 2,3,... to collect "
                         "multiple samples per cell on Hard tasks for within-cell variance.")
    args = ap.parse_args()

    # If a previous run crashed mid-stash, the scoring tree is orphaned in
    # %TEMP%\.bms_<hex>. Restore it before doing anything else so verify.py
    # can read meta.yaml later in this run.
    _recover_orphan_stashes()

    # Modes whose name pins a specific model override the --model flag default,
    # but only when the user did not pass --model explicitly.
    if args.model == ap.get_default("model") and args.mode in MODE_MODELS:
        args.model = MODE_MODELS[args.mode]

    # Same convention for budget: per-mode default kicks in only when the user
    # did not pass --budget explicitly.
    if args.budget == ap.get_default("budget") and args.mode in MODE_BUDGETS:
        args.budget = MODE_BUDGETS[args.mode]

    task      = args.task.replace("\\", "/")
    workspace = WORKSPACE / args.mode / task
    if args.rep is not None:
        if args.rep < 1:
            print(f"ERROR: --rep must be >= 1 (got {args.rep})")
            sys.exit(1)
        workspace = workspace / f"rep_{args.rep}"

    prompt_f = PROMPTS / f"{task}.md"
    if not prompt_f.exists():
        print(f"ERROR: prompt not found: {prompt_f}")
        sys.exit(1)

    # Fail closed: if verification is expected but the scoring key for this task is
    # unreachable, abort BEFORE spending API budget rather than producing a
    # silently-unscored run (the old behavior graded a missing key as a skip).
    # Content-aware — an empty SCORING_DIR fails too, since the meta.yaml is absent.
    # (2026-06-23 review benchmark-scoring audit: Reviewer 6/Reviewer 5/Reviewer 2 — fail-closed.)
    if not args.no_verify:
        scoring_key = SCORING_DIR / task / "meta.yaml"
        if not scoring_key.exists():
            print(f"ERROR: scoring key not found: {scoring_key}")
            print(f"  Cannot grade '{task}' — the Benchmark-scoring/ sibling repo is missing,")
            print(f"  BENCHMARK_SCORING_DIR is unset/wrong, or the scoring tree is empty.")
            print(f"  Clone it beside the Consilium repo, set BENCHMARK_SCORING_DIR, or")
            print(f"  pass --no-verify to run unscored.")
            sys.exit(2)

    if args.clean and workspace.exists():
        shutil.rmtree(workspace)
        print(f"  Cleaned: {workspace}")
    workspace.mkdir(parents=True, exist_ok=True)

    print(f"\nBenchmark Runner  |  {args.mode}  |  {task}")
    print("=" * 55)

    prefix = MODE_PREFIXES.get(args.mode, "")
    prompt = prompt_f.read_text(encoding="utf-8")

    # ── Template + workspace-path injection ───────────────
    # Prompts now contain only the task-unique description + declared
    # deliverables. Common boilerplate (constraints, workspace folder,
    # self-estimate trailer) lives in `prompts/templates/<category>.md` and
    # is appended at runtime. {WORKSPACE_PATH} is replaced with the actual
    # per-mode workspace so the model sees only its own folder, not a list of
    # six possibilities.
    category = task.split("/", 1)[0]   # "code" or "reasoning"
    template_f = PROMPTS / "templates" / f"{category}.md"
    template = template_f.read_text(encoding="utf-8") if template_f.exists() else ""
    workspace_rel = workspace.relative_to(BASE).as_posix() + "/"
    template = template.replace("{WORKSPACE_PATH}", workspace_rel)

    full_prompt = prefix + prompt + "\n" + template

    # Universal cache-buster: a per-task, per-invocation token so Anthropic's
    # prompt-cache misses between runs. Without it, back-to-back runs of the same
    # task can replay a stale cached prefix (observed on superpowers in
    # 2026-05-18: input_tokens=3-7 vs 800+ expected).
    #
    # Placement is mode-dependent. Slash-command modes (consilium_*, prefix
    # "/consilium ...") require the slash command at position 0 of the prompt or
    # `claude -p` does NOT expand it — the skill never loads and the run collapses
    # to bare Sonnet (num_turns=2, no .consilium/runs report). This was THE root
    # cause of the 2026-06-23 benchmark audit (deliberated=2 / skipped=41): the
    # cache-buster was prepended ABOVE `/consilium`, pushing it to line 2. For
    # those modes the token rides at the END instead (it still busts the cache;
    # only its position changes). Non-slash modes keep the leading token.
    cache_buster_top = (
        f"[run_id={task}@"
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}]"
    )
    # The /consilium slash command only auto-fires when it is the FIRST characters
    # of the message, so for slash-prefixed modes the cache-buster rides at the END
    # (it still busts the cache; only its position changes). Other modes prepend it.
    if prefix.startswith("/"):
        full_prompt = full_prompt + "\n\n" + cache_buster_top
    else:
        full_prompt = cache_buster_top + "\n" + full_prompt

    # For consilium modes: set CLAUDE_HEADLESS=1 so the skill skips user-facing
    # prompts (Step 0 stale_pendings, Step 2 irreversibility block, Step 5d retry,
    # Step 7 auto-pipeline). Deliverable enforcement is handled by Step 6.5 in
    # the Consilium SKILL.md itself.
    if args.mode.startswith("consilium_"):
        os.environ["CLAUDE_HEADLESS"] = "1"
        # Benchmark intent: measure the deliberation pipeline, not the trivial
        # short-circuit. CONSILIUM_FORCE_FULL=1 forces scope_gate.should_skip=False
        # so the Step 1.5 trivial-skip path can't collapse a reasoning task to a
        # direct answer. NOTE: this does NOT override the Conservator's scale_down
        # (Step 5 → skip Control); that path still writes a report with
        # pipeline_executed telemetry, which detect_pipeline_execution() records
        # so full-pipeline vs scale_down is visible, not silent (2026-06-23 review
        # condition: make the measured object honest rather than forcing 3 voices).
        os.environ["CONSILIUM_FORCE_FULL"] = "1"

    # superpowers skills tend to brainstorm / ask clarifying questions; in
    # auto mode we want a single non-interactive run for fair benchmarking.
    # IMPORTANT: avoid "dispatched as a subagent" framing — it triggers the
    # <SUBAGENT-STOP> guard in using-superpowers and silently disables all skills.
    if args.mode == "superpowers":
        # Cache-buster token. Without it, Anthropic prompt-cache served a
        # stale prefix on consecutive superpowers runs (2026-05-18 benchmark
        # symptom: input_tokens=3-7 on T01/T03/T04 vs 814 on T00 — task
        # content dropped from prompt). Per-task + per-invocation timestamp
        # guarantees a unique prefix hash.
        cache_buster = f"[run_id={task}@{datetime.now(timezone.utc).isoformat(timespec='seconds')}]"
        full_prompt = (
            f"BENCHMARK NON-INTERACTIVE RUN {cache_buster} — Skills are active "
            "and MUST be used. "
            "This is a headless single-shot run: do NOT invoke skills that require "
            "user input (superpowers:brainstorming, superpowers:writing-plans, "
            "superpowers:receiving-code-review). "
            "All other skills (TDD, consilium, verification-before-completion, "
            "systematic-debugging) SHOULD be invoked when relevant. "
            "Do NOT ask clarifying questions — state assumptions explicitly.\n\n"
            + full_prompt
        )

    # ── claude -p run ───────────────────────────────────
    response, usage, error_info, raw_json = auto_run(
        workspace, full_prompt, args.model, args.effort, args.budget,
    )

    self_est  = parse_self_estimate(response)
    questions = count_questions(response)

    print(f"\n  Model:        {usage.get('model', '?')}")
    print(f"  Cost:        ${usage.get('cost', '?')}")
    print(f"  API duration: {usage.get('api_duration', '?')}")
    print(f"  Wall:         {usage.get('wall', '?')}")
    print(f"  Input:        {usage.get('input', '?')} tokens")
    print(f"  Output:       {usage.get('output', '?')} tokens")
    print(f"  Cache read:   {usage.get('cache_read', '?')}")
    print(f"  Cache write:  {usage.get('cache_write', '?')}")
    print(f"  Num turns:    {usage.get('num_turns', '?')}")
    print(f"  Workspace lines: {usage.get('lines_added', '?')}")
    print(f"  Questions:    {questions}")
    if error_info and error_info.get("error"):
        print(f"  ! Halted:     {error_info.get('message', error_info['error'])}")

    # ── Deliverable extraction (harness-level fallback) ──
    # If the prompt declared output files and the model emitted them as
    # fenced code blocks in chat instead of calling Write, materialize
    # them now. Idempotent — skips files the model already wrote.
    # See scripts/extract_deliverables.py + design audit
    # an internal design audit.
    if not (error_info and error_info.get("error")):
        try:
            deliv_statuses = extract_deliverables.extract_and_write_from_response(
                prompt, response, workspace,
            )
        except Exception as exc:
            print(f"  ! extract_deliverables crashed: {exc}")
            deliv_statuses = {}
        if deliv_statuses:
            print(f"\n  Deliverable extraction:")
            for fname, status in deliv_statuses.items():
                marker = "+" if status in ("written", "already_exists") else "!"
                print(f"    {marker} {fname}: {status}")

    # ── Deliverable line count (calibration metric) ──
    # Sum lines in the declared deliverable files (post-extraction). This
    # is the actual value compared against the model's self-estimated
    # `Estimated deliverable lines: ~X` from its response trailer.
    try:
        declared = extract_deliverables.extract_declared_files(prompt)
    except Exception:
        declared = []
    usage["deliverable_lines"] = str(count_deliverable_lines(workspace, declared))
    if declared:
        print(f"  Deliverable lines: {usage['deliverable_lines']} "
              f"({', '.join(declared)})")

    verify_report = None
    if not args.no_verify and not (error_info and error_info.get("error")):
        print(f"\n  Running verification...")
        try:
            verify_report = verify_engine.run_verification(workspace, task)
        except Exception as e:
            print(f"  ! verification crashed: {e}")
            verify_report = {"ok": False, "reason": f"verifier exception: {e}",
                             "score": 0, "max_score": "?"}
        if verify_report is None:
            print(f"  (no verify/ folder for this task -- skipping)")
        else:
            print(f"  Verification: {verify_report.get('kind', '?')} -> "
                  f"score {verify_report.get('score', '?')} / "
                  f"{verify_report.get('max_score', '?')}")
            if not verify_report.get("ok"):
                print(f"  ! Reason: {verify_report.get('reason', '?')}")

    write_result(workspace, args.mode, task, usage, self_est, response,
                 questions, error_info=error_info, raw_json=raw_json,
                 verify_report=verify_report)

    if args.mode.startswith("consilium_") and response:
        detect_pipeline_execution(args.mode, response, workspace, raw_json)
        fix_pend_headless(response)
        if args.mode == "consilium_trias":
            from check_trias_parallelism import check as _check_trias_par, update_pipeline_audit as _update_audit
            _verdict = _check_trias_par(workspace)
            if _verdict is not None:
                _update_audit(workspace, _verdict)

    print(f"\nDone. Open RESULT.md to fill in the scoring.")
    print(f"  {workspace / 'RESULT.md'}")

if __name__ == "__main__":
    main()
