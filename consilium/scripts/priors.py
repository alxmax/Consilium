"""Load priors for a deliberation from FEEDBACK.html and runs/*.json.

Emits a small JSON block to stdout that the deliberation can paste as
soft priors at step 1. Reuses parse_feedback / parse_runs from feedback.py
so the parsing stays single-source.

Signals computed:
- recent: last N FEEDBACK entries (newest first; N defaults to 10)
- counts: outcome tally over the recent slice
- bad_rate: BAD / (OK + BAD + OVR), over ``[confirmed]`` rows only
- unconfirmed_count: OK/BAD/OVR rows without the marker — self-assigned at
  log time, excluded from the rates
- stale_pendings: up to STALE_PEND_CAP entries from the *full* FEEDBACK list
  (not just recent) whose outcome is PEND and whose date is older than
  STALE_PEND_DAYS — surfaces entries needing retrospective close at step 0
- missing_feedback_runs: runs/*.json files with NO matching FEEDBACK row
  (auto-logging was never called for them) — surfaces feedback gaps

The priors are advisory. Prompts in prompts/*.md remain authoritative.

CLI:
    python scripts/priors.py
    python scripts/priors.py --n 5
    python scripts/priors.py --no-runs
    python scripts/priors.py --feedback-file path/to/FEEDBACK.html
    python scripts/priors.py --runs-dir path/to/runs/
"""
# implements: CONSILIUM-PRIORS-001

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_FB_PATH = ROOT / "scripts" / "feedback.py"
_spec = importlib.util.spec_from_file_location("consilium_feedback", _FB_PATH)
assert _spec and _spec.loader
_feedback = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_feedback)

FEEDBACK = _feedback.FEEDBACK
RUNS = _feedback.RUNS
parse_feedback = _feedback.parse_feedback
parse_runs = _feedback.parse_runs

from version import (  # noqa: E402 — sibling script, scripts/ on path
    prompts_changed_since,
)
from utils import (  # noqa: E402 — sibling script, scripts/ on path
    force_utf8_streams,
)

TOKEN_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
STOPWORDS = {
    "the", "and", "with", "from", "this", "that", "was", "were", "but",
    "for", "into", "than", "what", "when", "where", "after", "before",
    "still", "just", "not", "are", "shipped", "dropped", "real", "fine",
}

# PEND entries older than this many days are surfaced at Step 0 so the user
# is prompted to close them retroactively. Was 7 — reduced to 2 because audits
# showed 40% of feedback rows reached PEND state and were forgotten before the
# week-long window expired. A two-day cutoff matches a typical "next session"
# cadence, which is when context for a deliberation is still recoverable.
STALE_PEND_DAYS = 2
STALE_PEND_CAP = 5
CONFIRMED_MARKER = "[confirmed]"
# Outcome rows whose note carries CONFIRMED_MARKER reflect reality (the chosen
# approach was applied and verified), not an impression logged right after the
# deliberation. Rates are computed from these rows only: most historical OK rows
# were auto-assigned from confidence >= 0.7, which measures agreement, not
# outcome.
_RATED = ("OK", "BAD", "OVR")


def _rel_or_str(path: Path) -> str:
    """Return path relative to ROOT, or absolute str if outside ROOT."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _outcome_counts(entries: list[dict]) -> Counter:
    return Counter(e["outcome"] for e in entries)


def _is_confirmed(entry: dict) -> bool:
    return CONFIRMED_MARKER in (entry.get("note") or "")


def _rates(entries: list[dict]) -> dict:
    rated_rows = [
        e for e in entries if e["outcome"] in _RATED and _is_confirmed(e)
    ]
    unconfirmed = sum(
        1 for e in entries
        if e["outcome"] in _RATED and not _is_confirmed(e)
    )
    rated = len(rated_rows)
    if not rated:
        return {
            "bad_rate": None,
            "rated_count": 0,
            "confirmed_count": 0,
            "unconfirmed_count": unconfirmed,
        }
    counts = _outcome_counts(rated_rows)
    return {
        "bad_rate": counts.get("BAD", 0) / rated,
        "rated_count": rated,
        "confirmed_count": rated,
        "unconfirmed_count": unconfirmed,
    }


def find_missing_feedback_runs(
    runs_dir: Path, feedback_entries: list[dict], cap: int = 5
) -> list[dict]:
    """Surface runs/*.json files with NO matching FEEDBACK row.

    Primary match: run_path appears in the .run_path_map.json sidecar written
    by log_feedback.py. Fallback (legacy runs not in sidecar): (date,
    chosen[:80]) appears in a feedback row. The fallback can produce false
    negatives when two runs on the same day share a chosen prefix, which is
    why the sidecar is preferred.
    """
    if not runs_dir.exists():
        return []

    # Load sidecar: maps fingerprint → "runs/<file>.json"
    sidecar_path = runs_dir / ".run_path_map.json"
    try:
        sidecar: dict[str, str] = json.loads(
            sidecar_path.read_text(encoding="utf-8-sig")
        )
    except (json.JSONDecodeError, OSError):
        sidecar = {}
    logged_run_paths: set[str] = set(sidecar.values())

    fb_keys: set[tuple[str, str]] = set()
    for e in feedback_entries:
        chosen = e.get("chosen") or ""
        fb_keys.add((e.get("date", ""), chosen[:80]))

    missing: list[dict] = []
    date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})")
    for run_file in sorted(runs_dir.glob("*.json"), reverse=True):
        m = date_re.match(run_file.name)
        if not m:
            continue
        d = m.group(1)
        rel = f"runs/{run_file.name}"
        # Prefer sidecar match (exact, no collision risk)
        if rel in logged_run_paths:
            continue
        try:
            data = json.loads(run_file.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            # Loud, not silent: a BOM/corrupt run that can't be read is
            # invisible to the missing-feedback check — surface it instead
            # of swallowing.
            print(
                f"[priors] warning: skipping unreadable "
                f"{run_file.name}: {e}",
                file=sys.stderr,
            )
            continue
        # Only canonical reports are expected to have a FEEDBACK row. Non-report
        # artifacts saved under runs/ (e.g. Trias personality sub-runs, which
        # carry `chose`/`personality` instead) lack chosen_approach — a field
        # validate_report requires on every real report — so skip them rather
        # than flag a false orphan.
        if not isinstance(data, dict) or "chosen_approach" not in data:
            continue
        chosen = data.get("chosen_approach")
        chosen_s = "null" if chosen is None else str(chosen)
        # Fallback: legacy rows without sidecar entry
        if (d, chosen_s[:80]) in fb_keys:
            continue
        missing.append({"run": run_file.name, "date": d, "chosen": chosen_s})
        if len(missing) >= cap:
            break
    return missing


def _top_keywords(entries: list[dict], k: int = 5) -> list[str]:
    tokens: Counter[str] = Counter()
    for e in entries:
        for tok in TOKEN_RE.findall(e.get("note", "").lower()):
            if tok in STOPWORDS:
                continue
            tokens[tok] += 1
    return [w for w, _ in tokens.most_common(k)]


def find_stale_pendings(
    entries: list[dict], days_old: int = STALE_PEND_DAYS
) -> list[dict]:
    cutoff = (date.today() - timedelta(days=days_old)).isoformat()
    return [
        {"date": e["date"], "context": e["context"], "chosen": e["chosen"]}
        for e in entries
        if e.get("outcome") == "PEND"
        and e.get("date", "")
        and e["date"] < cutoff
    ][:STALE_PEND_CAP]


_PRIOR_MATCH_MIN_LABEL_LEN = 8
_PRIOR_MATCH_WINDOW_DAYS = 30
_PRIOR_MATCH_OUTCOMES = {"OK"}


def _find_prior_match(
    label: str,
    entries: list[dict],
    window_days: int = _PRIOR_MATCH_WINDOW_DAYS,
) -> dict | None:
    """Return the most recent authoritative FEEDBACK entry whose context
    contains label.

    Returns None when label is too short (< 8 chars after strip) or no
    match exists within window_days. Scans entries newest-first so the
    most recent match wins.
    Only entries with outcome "OK" AND CONFIRMED_MARKER qualify —
    PEND/BAD/OVR and auto-assigned (unconfirmed) OK do not: passthrough
    skips re-deliberation, so it must rest on a verified outcome. (GO is
    a review verdict, never a FEEDBACK outcome, so it can never match.)
    """
    if len(label.strip()) < _PRIOR_MATCH_MIN_LABEL_LEN:
        return None
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    needle = label.strip().lower()
    for entry in reversed(entries):
        if entry.get("date", "") < cutoff:
            continue
        if entry.get("outcome") not in _PRIOR_MATCH_OUTCOMES:
            continue
        if not _is_confirmed(entry):
            continue
        context = (entry.get("context") or "").lower()
        if needle in context:
            return {
                "label": label,
                "date": entry.get("date"),
                "outcome": entry.get("outcome"),
                "chosen": entry.get("chosen"),
            }
    return None


def _prompt_drift(runs_dir: Path) -> dict | None:
    """Step-0 advisory: did prompts/ or modes/ change since the
    most-recent prior run?

    Reads ``telemetry.consilium_ref`` from the newest run that carries
    one (older runs predate the provenance feature) and diffs it
    against HEAD. Returns a note only when a resolvable baseline
    exists AND files changed; otherwise None. Never raises —
    ``prompts_changed_since`` guards an empty/"unknown"/dirty/unreachable
    ref.
    """
    if not runs_dir.exists():
        return None
    for run_file in sorted(runs_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(run_file.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        ref = (data.get("telemetry") or {}).get("consilium_ref")
        if not ref:
            continue
        # Newest stamped run is the baseline; compute drift against it and stop.
        n = prompts_changed_since(ref)
        return (
            {
                "changed_files": n,
                "since_ref": ref,
                "since_run": run_file.name,
            }
            if n > 0
            else None
        )
    return None


def get_memory_summary(
    label: str | None = None, n: int = 10, feedback: Path = FEEDBACK
) -> str | None:
    """Return a compact plain-text memory context block for Conservator
    injection.

    Produces 2–3 lines from recent FEEDBACK outcomes and, when a label
    is given, any prior deliberation match. Intended to be prepended
    to the Conservator's input context (not its authoritative prompt).
    Returns None when no FEEDBACK data is available.
    """
    entries = parse_feedback(feedback)
    if not entries:
        return None
    recent = entries[-n:]
    counts = _outcome_counts(recent)
    rates = _rates(recent)
    lines: list[str] = []
    ok, bad, ovr, pend = (
        counts.get("OK", 0),
        counts.get("BAD", 0),
        counts.get("OVR", 0),
        counts.get("PEND", 0),
    )
    br = rates.get("bad_rate")
    br_str = (
        f", confirmed bad_rate={br:.2f} (n={rates['rated_count']})"
        if br is not None
        else ""
    )
    lines.append(
        f"[Prior runs: last {len(recent)} outcomes — OK={ok}, "
        f"BAD={bad}, OVR={ovr}, PEND={pend}{br_str}]"
    )
    if label is not None:
        match = _find_prior_match(label, entries)
        if match:
            lines.append(
                f"[Prior match for '{label}': "
                f"chosen='{match['chosen']}', date={match['date']},"
                f" outcome={match['outcome']} — assess whether this "
                f"approach is still valid.]"
            )
    keywords = _top_keywords(recent, k=3)
    if keywords:
        lines.append(
            f"[Recurring patterns in recent notes: {', '.join(keywords)}]"
        )
    return "\n".join(lines)


def build_priors(
    n: int = 10,
    include_runs: bool = True,
    headless: bool = False,
    label: str | None = None,
    feedback: Path = FEEDBACK,
    runs_dir: Path = RUNS,
) -> dict:
    entries = parse_feedback(feedback)
    recent = entries[-n:]
    counts = dict(_outcome_counts(recent))
    pend_pressure = counts.get("PEND", 0) / len(recent) if recent else 0.0
    out: dict = {
        "source": {
            "feedback_path": _rel_or_str(feedback),
            "feedback_total": len(entries),
            "feedback_window": len(recent),
        },
        "recent": recent,
        "counts": counts,
        **_rates(recent),
        "pend_pressure": round(pend_pressure, 2),
        "stale_pendings": find_stale_pendings(entries),
    }
    if include_runs:
        runs = parse_runs(runs_dir)
        out["source"]["runs_path"] = _rel_or_str(runs_dir)
        out["source"]["runs_total"] = len(runs)
        out["missing_feedback_runs"] = find_missing_feedback_runs(
            runs_dir, entries
        )
        drift = _prompt_drift(runs_dir)
        if drift:
            out["prompt_drift"] = drift
    if label is not None:
        out["prior_deliberation_match"] = _find_prior_match(label, entries)
    if headless:
        out["stale_pendings"] = []
        out["missing_feedback_runs"] = []
        out["headless_mode"] = True
    return out


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--n", type=int, default=10,
        help="number of recent FEEDBACK entries to summarize",
    )
    ap.add_argument(
        "--no-runs", dest="runs", action="store_false",
        help="skip scanning runs/*.json",
    )
    ap.add_argument(
        "--headless", action="store_true",
        help="suppress stale_pendings and missing_feedback_runs for "
        "non-interactive/CI runs",
    )
    ap.add_argument(
        "--feedback-file", metavar="PATH",
        help="override FEEDBACK.html path (default: "
        "<repo>/FEEDBACK.html). Note: audit_feedback.py uses "
        "--feedback for the same concept.",
    )
    ap.add_argument(
        "--runs-dir", metavar="PATH",
        help="override runs/ directory path (default: <repo>/runs)",
    )
    ap.add_argument(
        "--label", metavar="TEXT",
        help="check FEEDBACK for a recent authoritative run matching "
        "this task label; emits prior_deliberation_match field",
    )
    ap.add_argument(
        "--memory-summary", action="store_true",
        help="output a compact plain-text memory context block for "
        "Conservator injection (not JSON); combine with --label for "
        "prior-match line",
    )
    args = ap.parse_args(argv)

    feedback = (
        Path(args.feedback_file).resolve() if args.feedback_file else FEEDBACK
    )
    runs_dir = Path(args.runs_dir).resolve() if args.runs_dir else RUNS

    # Explicit signals only. stdin is never a tty under Claude Code's Bash
    # tool, so an isatty() check marked every interactive session headless
    # and silently suppressed stale_pendings / missing_feedback_runs.
    _headless = (
        args.headless
        or os.environ.get("CONSILIUM_HEADLESS") == "1"
        or os.environ.get("CLAUDE_HEADLESS") == "1"
    ) and os.environ.get("CONSILIUM_HEADLESS") != "0"
    if args.memory_summary:
        summary = get_memory_summary(
            label=args.label, n=args.n, feedback=feedback
        )
        if summary:
            sys.stdout.write(summary + "\n")
        return 0
    priors = build_priors(
        n=args.n,
        include_runs=args.runs,
        headless=_headless,
        label=args.label,
        feedback=feedback,
        runs_dir=runs_dir,
    )
    json.dump(priors, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
