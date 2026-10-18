"""Shared utilities for Consilium scripts.

All functions are stdlib-only. Scripts import from this module instead of
defining their own copies. Each script remains a stand-alone executable.
"""
# implements: CONSILIUM-UTILS-001
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator


# ---------------------------------------------------------------------------
# Canonical data locations (single source of truth).
#
# All deliberation state lives under .consilium/ in the project being worked on
# (the current working directory — where SKILL.md has the orchestrator write
# its reports), or under $CONSILIUM_DATA_DIR when that is set:
#   .consilium/runs/*.json              — one file per deliberation (episodic)
#   .consilium/runs/.run_path_map.json  — fingerprint -> run-path sidecar
#   .consilium/FEEDBACK.html            — append-only outcome journal (long)
# Never the install directory: a plugin cache or an APM-deployed skill folder
# is replaced on every update, which would reset the journal each version.
#
# Scripts import these as their DEFAULT; CLI flags (--runs-dir/--feedback)
# still override. run-path strings stored in the sidecar / FEEDBACK rows are
# relative to DATA_DIR (e.g. "runs/<file>.json"), so they keep resolving as
# long as runs/ and FEEDBACK.html stay siblings under DATA_DIR.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR_ENV = os.environ.get("CONSILIUM_DATA_DIR", "").strip()
DATA_DIR = (Path(_DATA_DIR_ENV).resolve() if _DATA_DIR_ENV
            else Path.cwd() / ".consilium")
RUNS_DIR = DATA_DIR / "runs"
FEEDBACK_PATH = DATA_DIR / "FEEDBACK.html"


def canonical_run_path(run_path: str) -> str:
    """Normalize a run-path to the DATA_DIR-relative sidecar key
    ``runs/<name>``.

    Run files are flat under ``RUNS_DIR`` with timestamped (unique) basenames,
    so the basename alone identifies a run. Callers may pass any of
    ``.consilium/runs/<f>.json``, ``runs/<f>.json``, or an absolute path — all
    collapse to the same ``runs/<f>.json`` key. This keeps sidecar / FEEDBACK
    keys stable regardless of how the orchestrator spelled the path, and is
    backward-compatible with the historical ``runs/<f>.json`` convention.
    """
    return f"runs/{Path(run_path.replace(chr(92), '/')).name}"


def force_utf8_streams() -> None:
    """Reconfigure stdin/stdout/stderr to UTF-8.

    Windows default encoding is cp1252; piping UTF-8 JSON through it
    mangles non-ASCII characters (ț, ș, ă) before any script sees them.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def is_headless() -> bool:
    """True when CLAUDE_HEADLESS=1 — orchestrator runs via `claude -p`
    without an interactive user.

    Skill workflow steps that emit user-facing prompts (Step 0 stale_pendings,
    Step 2 irreversibility, Step 5d retry, Step 7 auto-pipeline) MUST check
    this and fall through to a documented default instead. See
    SKILL.md §"Headless invariants" for the per-step contract.

    Pattern aligned with CONSILIUM_FORCE_FULL=1 in scope_gate.py: strict
    boolean check on string '1'. Other values (true/yes/0/empty) → False.
    """
    return os.environ.get("CLAUDE_HEADLESS") == "1"


def load_json_stdin(script_name: str) -> Any:
    """Read and parse JSON from stdin.

    On empty stdin or parse error, prints a clear usage hint and exits 2.
    Callers treat the return value as already-validated JSON (dict or list).

    Usage hint format:
        "<script_name>: no input — pipe a report file, e.g.:
         cat runs/<file>.json | python scripts/<script_name>"
    """
    raw = sys.stdin.read()
    # PowerShell 5.1 pipes prepend a UTF-8 BOM. force_utf8_streams reconfigures
    # stdin as plain utf-8 (not utf-8-sig), so the BOM survives as a leading
    # U+FEFF that str.strip() does NOT remove and json.loads rejects with
    # "Unexpected UTF-8 BOM". Strip it before both the empty-check and parse.
    raw = raw.lstrip("\ufeff")
    if not raw.strip():
        print(
            f"{script_name}: no input — pipe a report file, e.g.:\n"
            f"  cat runs/<file>.json | python scripts/{script_name}",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"{script_name}: invalid JSON — {exc}", file=sys.stderr)
        sys.exit(2)


def atomic_write_text(path, content: str, encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically.

    Uses a sibling ``NamedTemporaryFile`` in the same directory (same
    filesystem) so ``os.replace`` is atomic on both POSIX and Windows.
    ``flush()`` + ``os.fsync()`` guarantee the bytes hit storage before the
    rename, so a crash mid-write leaves the original intact rather than
    truncated — critical for long-term journals (FEEDBACK.html).

    The temp file is deleted on any error so no stale ``.tmp`` accumulates.
    """
    path = Path(path)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=path.stem + "_", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


if sys.platform == "win32":
    import msvcrt

    def _try_lock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fh) -> None:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh) -> None:
        fcntl.flock(fh, fcntl.LOCK_UN)


@contextlib.contextmanager
def feedback_lock(feedback_path, timeout: float = 30.0) -> Iterator[None]:
    """Hold an exclusive cross-process lock for one FEEDBACK.html transaction.

    ``atomic_write_text`` keeps a single write from tearing the file, but a
    read-modify-write (parse rows, change, re-render) still loses a
    concurrent writer's rows. Every writer of FEEDBACK.html and its
    ``runs/.run_path_map.json`` sidecar takes this lock around the WHOLE
    parse -> write sequence. The OS drops the lock when the holder dies, so a
    killed process never leaves it stuck. Raises ``TimeoutError`` after
    ``timeout`` seconds instead of waiting forever.
    """
    lock_path = Path(str(feedback_path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+b") as fh:
        if lock_path.stat().st_size == 0:
            fh.write(b"\0")
            fh.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                _try_lock(fh)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"feedback lock busy: {lock_path} (waited {timeout}s)"
                    ) from None
                time.sleep(0.05)
        try:
            yield
        finally:
            _unlock(fh)


_ISSUE_PENALTIES = {"low": 0.05, "medium": 0.15, "high": 0.30}


def issue_penalty(issue: object) -> float:
    """Return the score penalty for a single Control issue based on severity.

    Severity levels: low=0.05, medium=0.15 (default), high=0.30.
    If the issue dict has no severity field, 0.15 is used (backward-compatible).
    """
    if isinstance(issue, dict):
        return _ISSUE_PENALTIES.get(issue.get("severity", "medium"), 0.15)
    return 0.15


def validate_keys(data: dict, required: list[str], context: str) -> None:
    """Assert that *data* contains all keys in *required*.

    On missing key, raises ValueError with the context label. Callers that
    need a clean exit-code should catch ValueError in their main() wrapper.
    """
    if not isinstance(data, dict):
        raise ValueError(f"{context}: expected dict, got {type(data).__name__}")
    for key in required:
        if key not in data:
            raise ValueError(f"{context}: missing required field '{key}'")
