"""Find ``runs/*.json`` files that have no row in ``FEEDBACK.html`` and
offer to backfill.

The auto-log step at end of SKILL.md Step 6 is the only thing that
creates a FEEDBACK row. If it gets skipped — orchestrator crashes,
session ends abruptly, user closes terminal before final pipe — the
run exists on disk but the journal has no record of it. ``priors.py``
already surfaces the gap as ``missing_feedback_runs``; this script
gives you the tool to act on it.

By default the script only **lists** the gap. With ``--backfill`` it
appends a default PEND row for each missing run (using the same
note-derivation as ``log_feedback.py``) so ``priors.py``'s
``stale_pendings`` will surface them at the next Step 0 and the user
can close them with the standard PEND->OK/BAD prompt.

Two safety choices baked in:

- Outcome defaults to PEND. We don't guess OK retroactively just because
  the run looks well-shaped — a missing-feedback run is by definition
  one the user never rated.
- Existing rows are never overwritten. A run is matched (and so skipped)
  if any row has the same date AND same chosen_approach prefix.

CLI:
    python scripts/audit_feedback.py                  # just list
    python scripts/audit_feedback.py --backfill       # append PEND rows
    python scripts/audit_feedback.py --backfill --dry-run
"""
# implements: CONSILIUM-AUDIT-FEEDBACK-001
# Restored 2026-06-10 from 84632db^ — deleted as "dead" by static triage, but
# it is invoked via SKILL.md prose (Step 0 missing_feedback_runs remedy, Step 6
# final actions, headless invariants), which static reference analysis cannot
# see.

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from utils import (
    FEEDBACK_PATH,
    RUNS_DIR,
    atomic_write_text,
    feedback_lock,
    force_utf8_streams,
)


def _load_modules():
    here = Path(__file__).resolve().parent
    priors_spec = importlib.util.spec_from_file_location(
        "consilium_priors", here / "priors.py")
    assert priors_spec and priors_spec.loader
    priors_mod = importlib.util.module_from_spec(priors_spec)
    sys.modules["consilium_priors"] = priors_mod
    priors_spec.loader.exec_module(priors_mod)

    fb_spec = importlib.util.spec_from_file_location(
        "consilium_feedback", here / "feedback.py")
    assert fb_spec and fb_spec.loader
    fb_mod = importlib.util.module_from_spec(fb_spec)
    sys.modules["consilium_feedback"] = fb_mod
    fb_spec.loader.exec_module(fb_mod)

    log_spec = importlib.util.spec_from_file_location(
        "consilium_logfb", here / "log_feedback.py")
    assert log_spec and log_spec.loader
    log_mod = importlib.util.module_from_spec(log_spec)
    sys.modules["consilium_logfb"] = log_mod
    log_spec.loader.exec_module(log_mod)

    render_spec = importlib.util.spec_from_file_location(
        "consilium_render", here / "render_feedback_html.py")
    assert render_spec and render_spec.loader
    render_mod = importlib.util.module_from_spec(render_spec)
    sys.modules["consilium_render"] = render_mod
    render_spec.loader.exec_module(render_mod)

    return priors_mod, fb_mod, log_mod, render_mod


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", default=None,
                    help="path to runs/ (default: .consilium/runs)")
    ap.add_argument("--feedback", default=None,
                    help="path to FEEDBACK.html "
                         "(default: .consilium/FEEDBACK.html)")
    ap.add_argument("--backfill", action="store_true",
                    help="append PEND rows for each missing run")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --backfill: print plan but don't write")
    ap.add_argument(
        "--check", action="store_true",
        help="corpus-completeness gate: exit 1 if any run lacks a "
             "FEEDBACK row (read-only, no write). Use in CI / before "
             "building a calibration corpus.")
    return ap


def _print_dry_run(missing: list[dict], runs_dir: Path, log_mod) -> None:
    for m in missing:
        run_path_abs = runs_dir / m["run"]
        try:
            report = json.loads(
                run_path_abs.read_text(encoding="utf-8-sig"))
            entry = log_mod.build_entry(report, outcome="PEND")
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            print(f"  skip {m['run']}: {exc}", file=sys.stderr)
            continue
        if m.get("date"):
            entry["date"] = m["date"]
        print(f"  [dry-run] would append: {entry['date']} | "
              f"{entry['context']} | {entry['chosen']} | PEND | "
              f"{entry['note']}")
    print(f"\ndry-run: {len(missing)} rows would be appended.")


def _row_run_path(
    row: dict, run_map: dict[str, str], log_mod
) -> str | None:
    """Restore run_path for an existing row (same logic as
    log_feedback.append_entry)."""
    for fp, rp in run_map.items():
        run_id_candidate = Path(rp).name if rp else None
        fp_candidate = log_mod._fingerprint(
            row["date"], row["chosen"], row["context"],
            run_id=run_id_candidate
        )
        if fp_candidate == fp:
            return rp
    return None


def _backfill_entry(
    m: dict,
    runs_dir: Path,
    run_map: dict[str, str],
    known_run_paths: set[str],
    log_mod,
    render_mod,
):
    """Build the PEND Entry for one missing run, or None when skipped.
    Updates ``run_map`` / ``known_run_paths`` in place for accepted runs."""
    run_path_abs = runs_dir / m["run"]
    rel = f"runs/{m['run']}"
    try:
        report = json.loads(run_path_abs.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  skip {m['run']}: {exc}", file=sys.stderr)
        return None
    try:
        entry = log_mod.build_entry(report, outcome="PEND")
    except ValueError as exc:
        print(f"  skip {m['run']}: build_entry failed ({exc})",
              file=sys.stderr)
        return None
    if m.get("date"):
        entry["date"] = m["date"]
    # Dedup: skip if this run_path is already in the sidecar map.
    if rel in known_run_paths:
        print(f"  skip {m['run']}: duplicate fingerprint, "
              f"already in FEEDBACK.html", file=sys.stderr)
        return None
    # Accumulate the new Entry and update the sidecar map in-memory.
    run_id = Path(rel).name
    new_fp = log_mod._fingerprint(
        entry["date"], entry["chosen"], entry["context"], run_id=run_id)
    run_map[new_fp] = rel
    known_run_paths.add(rel)
    backfill_note = entry["note"] + "; backfilled"
    return render_mod.Entry(
        date=entry["date"],
        context=entry["context"],
        chosen=entry["chosen"],
        outcome=entry["outcome"],
        note=backfill_note,
        run_path=rel,
        vote_pattern=entry.get("vote_pattern", ""),
    )


def _backfill(
    missing: list[dict],
    runs_dir: Path,
    feedback_path: Path,
    fb_mod,
    log_mod,
    render_mod,
) -> None:
    with feedback_lock(feedback_path):
        appended = _backfill_locked(
            missing, runs_dir, feedback_path, fb_mod, log_mod, render_mod
        )

    print(f"\nbackfilled {appended} PEND row(s) into {feedback_path.name}.")
    print("close them retroactively with: python scripts/mark_outcome.py "
          "--run-path runs/<file>.json --outcome OK|BAD")


def _backfill_locked(
    missing: list[dict],
    runs_dir: Path,
    feedback_path: Path,
    fb_mod,
    log_mod,
    render_mod,
) -> int:
    # Batch backfill: read FEEDBACK.html once, accumulate all new Entry
    # objects, write once.  This avoids O(N²) read-render-write cycles.
    existing_rows = fb_mod.parse_feedback(feedback_path)
    run_map = log_mod._load_map(runs_dir)

    # Build a set of already-present run_paths for fast dedup.
    known_run_paths: set[str] = set(run_map.values())

    accumulated: list = [
        render_mod.Entry(
            **row, run_path=_row_run_path(row, run_map, log_mod)
        )
        for row in existing_rows
    ]

    appended = 0
    for m in missing:
        new_entry = _backfill_entry(
            m, runs_dir, run_map, known_run_paths, log_mod, render_mod
        )
        if new_entry is None:
            continue
        accumulated.append(new_entry)
        appended += 1

    if appended > 0:
        # Single write for all new entries.
        atomic_write_text(
            feedback_path, render_mod.render(accumulated, runs_dir))
        log_mod._save_map(runs_dir, run_map)
    return appended


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    args = _build_parser().parse_args(argv)

    priors_mod, fb_mod, log_mod, render_mod = _load_modules()

    runs_dir = Path(args.runs_dir) if args.runs_dir else RUNS_DIR
    feedback_path = Path(args.feedback) if args.feedback else FEEDBACK_PATH

    entries = fb_mod.parse_feedback(feedback_path)
    missing = priors_mod.find_missing_feedback_runs(runs_dir, entries, cap=999)

    if not missing:
        print("no missing feedback rows — every run is logged.")
        return 0

    print(f"runs without feedback rows: {len(missing)}")
    for m in missing:
        print(f"  {m['run']}  date={m['date']}  chosen={m['chosen']}")

    # Completeness gate: a missing row is silent corpus loss (a run that never
    # got an outcome can never enter a labeled calibration corpus).
    # validate_report is a pure per-report gate and cannot see FEEDBACK.html,
    # so the corpus-level check lives here. (review 2026-05-27 — Reviewer 6
    # D5.)
    if args.check:
        print(f"\nFAIL: {len(missing)} run(s) without a FEEDBACK row. "
              f"Run with --backfill to append default PEND rows.",
              file=sys.stderr)
        return 1

    if not args.backfill:
        print("\nrun with --backfill to append default PEND rows for "
              "these runs.")
        return 0

    if args.dry_run:
        _print_dry_run(missing, runs_dir, log_mod)
        return 0

    _backfill(missing, runs_dir, feedback_path, fb_mod, log_mod, render_mod)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
