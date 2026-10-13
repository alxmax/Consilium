"""Retroactively mark a deliberation outcome based on what happened in reality.

Closes the loop opened by ``log_feedback.py``. The initial outcome that
gets logged at end of Step 6 is *subjective* — it reflects the user's
gut feeling immediately after the deliberation. Production reality may
flip it days later: a chosen approach that looked fine can cause a bug
in prod (=> BAD), or an override that felt risky can turn out to have
been the right call (=> OK).

This script updates an existing FEEDBACK.html row in place:

- Outcome cell is replaced (e.g. PEND -> BAD, OK -> BAD).
- Note is annotated with ``[confirmed]`` so ``priors.py`` can weight
  outcome-confirmed rows higher than subjective ones (signals quality).
- An optional ``--reason`` is appended to the note for future audits.

Row matching strategy (tried in order):

1. ``--run-path runs/<file>.json`` — looks up the entry via the sidecar
   ``runs/.run_path_map.json`` populated by ``log_feedback.py``.
2. ``--date YYYY-MM-DD --chosen <id>`` — direct match against the row.
3. If neither match: exits 1 with the list of candidate rows from the
   most recent N entries so the caller can pick the right one.

If --run-path matches multiple feedback rows (a run logged twice), all
matched rows are updated (rare but possible after a re-render).

CLI:
    python scripts/mark_outcome.py --run-path runs/2026-05-12_foo.json
        --outcome BAD --reason "broke prod migration"
    python scripts/mark_outcome.py --date 2026-05-12 --chosen approach_a
        --outcome OK
    python scripts/mark_outcome.py --run-path runs/2026-05-12_foo.json
        --outcome BAD --dry-run
"""
# implements: CONSILIUM-MARK-OUTCOME-001

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from utils import (
    FEEDBACK_PATH,
    atomic_write_text,
    canonical_run_path,
    force_utf8_streams,
)


CONFIRMED_MARKER = "[confirmed]"
RUN_PATH_MAP = ".run_path_map.json"


def _load_log_mod():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "consilium_log_feedback", here / "log_feedback.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["consilium_log_feedback"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_modules():
    here = Path(__file__).resolve().parent
    fb_spec = importlib.util.spec_from_file_location(
        "consilium_feedback", here / "feedback.py"
    )
    assert fb_spec and fb_spec.loader
    fb_mod = importlib.util.module_from_spec(fb_spec)
    sys.modules["consilium_feedback"] = fb_mod
    fb_spec.loader.exec_module(fb_mod)

    render_spec = importlib.util.spec_from_file_location(
        "consilium_render", here / "render_feedback_html.py"
    )
    assert render_spec and render_spec.loader
    render_mod = importlib.util.module_from_spec(render_spec)
    sys.modules["consilium_render"] = render_mod
    render_spec.loader.exec_module(render_mod)
    return fb_mod, render_mod


def _load_run_map(runs_dir: Path) -> dict[str, str]:
    map_path = runs_dir / RUN_PATH_MAP
    if not map_path.exists():
        return {}
    try:
        return json.loads(map_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _falsifier_from_run(run_file: Path) -> str | None:
    """Read Control's declared falsifier (strongest_objection.reason) from a
    persisted run report's deliberation_log. Returns None when the file is
    unreadable or the field is absent (pre-1.6.0 runs)."""
    try:
        data = json.loads(run_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    for step in data.get("deliberation_log") or []:
        if isinstance(step, dict) and step.get("step") == "control":
            so = step.get("strongest_objection")
            if isinstance(so, dict):
                reason = so.get("reason")
                if isinstance(reason, str) and reason.strip():
                    return reason.strip()
    return None


def _annotate_note(note: str, reason: str | None, outcome: str = "") -> str:
    parts = [p.strip() for p in note.split(";") if p.strip()]
    if outcome == "PEND_HEADLESS":
        if "benchmark_headless" not in parts:
            parts.append("benchmark_headless")
    elif outcome in ("PEND", "CLOSED_UNVERIFIED"):
        # Not a verified outcome: drop any stale marker instead of adding one.
        parts = [p for p in parts if p != CONFIRMED_MARKER]
    else:
        if CONFIRMED_MARKER not in parts:
            parts.append(CONFIRMED_MARKER)
    parts = [p for p in parts if not p.startswith("outcome_reason=")]
    if reason:
        clean = reason.replace("|", "/").replace("\n", " ").strip()
        if clean:
            parts.append(f"outcome_reason={clean}")
    return "; ".join(parts)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--feedback",
        default=None,
        help="path to FEEDBACK.html (default: .consilium/FEEDBACK.html)",
    )
    ap.add_argument(
        "--run-path",
        default=None,
        help="match the row whose sidecar maps to this run path",
    )
    ap.add_argument(
        "--date", default=None, help="match by date (with --chosen)"
    )
    ap.add_argument(
        "--chosen", default=None, help="match by chosen id (with --date)"
    )
    ap.add_argument(
        "--outcome",
        choices=(
            "OK", "BAD", "OVR", "PEND", "PEND_HEADLESS", "CLOSED_UNVERIFIED"
        ),
        required=True,
        help=(
            "new outcome value; OK/BAD/OVR get the [confirmed] marker; "
            "CLOSED_UNVERIFIED closes a PEND without evidence (stale "
            "cleanup); PEND_HEADLESS requires --benchmark flag"
        ),
    )
    ap.add_argument("--benchmark", action="store_true",
        help="required when --outcome PEND_HEADLESS; marks entry as "
             "headless benchmark run")
    ap.add_argument(
        "--reason",
        default=None,
        help="short string appended to note as outcome_reason=...",
    )
    ap.add_argument("--auto-suggest", action="store_true",
        help="when --reason is omitted, read Control's declared falsifier "
             "(strongest_objection.reason) from the run JSON and use it as "
             "the reason")
    ap.add_argument(
        "--dry-run", action="store_true", help="print matched rows; don't write"
    )
    return ap


def _apply_auto_suggest(args: argparse.Namespace) -> None:
    """Consumer for the declared falsifier (design review 2026-07-07_011914:
    consumer-first). Explicit --reason always wins; auto-suggest only fills
    the gap, and degrades gracefully on runs that predate the field."""
    if not (args.auto_suggest and not args.reason and args.run_path):
        return
    run_file = Path(args.run_path)
    if not run_file.exists():
        fb_dir = (
            Path(args.feedback).parent
            if args.feedback
            else FEEDBACK_PATH.parent
        )
        run_file = fb_dir / "runs" / Path(args.run_path).name
    falsifier = _falsifier_from_run(run_file)
    if falsifier:
        args.reason = f"falsifier: {falsifier}"
        print(
            "auto-suggest: using declared falsifier as reason: "
            f"{falsifier}"
        )
    else:
        print(
            "auto-suggest: no declared falsifier in run file; "
            "proceeding without reason"
        )


def _load_entries(feedback_path: Path, fb_mod, render_mod) -> list:
    """Parse FEEDBACK.html into render Entry rows with run_path attached.

    Attach run_path via the CANONICAL fingerprint. The sidecar key encodes
    run_id (= run-file basename), so derive it from each stored run_path and
    recompute the row fingerprint with it (mirrors
    audit_feedback._row_run_path).
    The old context[:30]/no-run_id local copy never matched, so --run-path
    lookup always failed for any context > 30 chars.
    """
    runs_dir = feedback_path.parent / "runs"
    existing = fb_mod.parse_feedback(feedback_path)
    run_map = _load_run_map(runs_dir)
    log_mod = _load_log_mod()

    def _row_run_path(row: dict) -> str | None:
        for fp, rp in run_map.items():
            run_id = Path(rp).name if rp else None
            if (
                log_mod._fingerprint(
                    row["date"], row["chosen"], row["context"], run_id=run_id
                )
                == fp
            ):
                return rp
        return None

    return [
        render_mod.Entry(**row, run_path=_row_run_path(row))
        for row in existing
    ]


def _match_rows(entries: list, args: argparse.Namespace) -> list[int]:
    """Indices of the rows selected by --run-path, else --date + --chosen."""
    matched_idx: list[int] = []
    if args.run_path:
        # Normalize to the canonical sidecar key (runs/<basename>) so any of
        # .consilium/runs/<f>.json, runs/<f>.json, or an absolute path matches
        # the stored form. Run basenames are timestamped and unique.
        wanted = canonical_run_path(args.run_path)
        for i, e in enumerate(entries):
            if not e.run_path:
                continue
            if canonical_run_path(e.run_path) == wanted:
                matched_idx.append(i)
    else:
        for i, e in enumerate(entries):
            if e.date == args.date and e.chosen == args.chosen:
                matched_idx.append(i)
    return matched_idx


def _print_no_match(entries: list, args: argparse.Namespace) -> None:
    print(f"mark_outcome: no row matched", file=sys.stderr)
    print(
        f"  query: run_path={args.run_path!r} date={args.date!r} "
        f"chosen={args.chosen!r}",
        file=sys.stderr,
    )
    print(f"  last 5 rows for reference:", file=sys.stderr)
    for e in entries[-5:]:
        print(
            f"    {e.date} | {e.chosen} | {e.outcome} | "
            f"run_path={e.run_path}",
            file=sys.stderr,
        )


def _update_rows(
    entries: list, matched_idx: list[int], args: argparse.Namespace
) -> int:
    """Update outcome + annotate note on matched rows; returns the count."""
    updated = 0
    for i in matched_idx:
        e = entries[i]
        if e.outcome == args.outcome:
            print(f"skip [{i}]: already {args.outcome}")
            continue
        if args.outcome == "PEND_HEADLESS" and e.outcome != "PEND":
            print(
                f"skip [{i}]: outcome is {e.outcome}, only PEND rows can be "
                f"converted to PEND_HEADLESS",
                file=sys.stderr,
            )
            continue
        old_outcome = e.outcome
        e.outcome = args.outcome
        e.note = _annotate_note(e.note, args.reason, outcome=args.outcome)
        print(
            f"matched [{i}]: {e.date} | {e.chosen} | {old_outcome} -> "
            f"{args.outcome}"
        )
        updated += 1
    return updated


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    args = _build_parser().parse_args(argv)

    if not args.run_path and not (args.date and args.chosen):
        print(
            "mark_outcome: provide --run-path OR (--date AND --chosen)",
            file=sys.stderr,
        )
        return 1

    _apply_auto_suggest(args)

    if args.outcome == "PEND_HEADLESS" and not args.benchmark:
        print(
            "mark_outcome: --outcome PEND_HEADLESS requires --benchmark flag",
            file=sys.stderr,
        )
        return 1

    fb_mod, render_mod = _load_modules()

    feedback_path = Path(args.feedback) if args.feedback else FEEDBACK_PATH
    if not feedback_path.exists():
        print(
            f"mark_outcome: feedback file missing: {feedback_path}",
            file=sys.stderr,
        )
        return 1
    runs_dir = feedback_path.parent / "runs"

    entries = _load_entries(feedback_path, fb_mod, render_mod)

    matched_idx = _match_rows(entries, args)
    if not matched_idx:
        _print_no_match(entries, args)
        return 1

    updated = _update_rows(entries, matched_idx, args)

    if args.dry_run:
        print("(dry-run; no write)")
        return 0

    if not updated:
        return 0

    atomic_write_text(feedback_path, render_mod.render(entries, runs_dir))
    print(f"updated {updated} row(s) in {feedback_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
