"""Auto-append an entry to FEEDBACK.html from a deliberation report.

Reads a deliberation report (JSON) from stdin, derives the standard
feedback entry, and appends it to FEEDBACK.html (creating the file if
missing). Removes the friction of asking the user for the entry at end
of Step 6 — the agent calls this directly.

Entry format:
    {date, context, chosen, outcome, note} appended as <tr> to FEEDBACK.html.

Auto-fill rules:
- data    : today's date in ISO format
- context : success_criterion truncated to 60 chars (with `...`)
- chosen  : chosen_approach (or literal "null" / "skipped")
- outcome : controlled by --outcome flag (default PEND). A deliberation's
            outcome is unknown when it is logged, so Step 6 logs PEND;
            OK needs --confirmed (verification passed / user confirmed),
            confidence < 0.7 + user picks alt -> OVR with --override-target,
            headless -> PEND_HEADLESS. PEND rows close later via
            mark_outcome.py.
- note    : auto-derived from report shape, max 80 chars:
            * skipped report      -> "skipped: <skip_reason>"
            * all-vetoed (chosen=null) -> "all vetoed; relaxed=<X>"
            * normal              -> "<N> cand, <K> vetoed, conf=<X>, mode=<Y>"
            When --outcome=OVR and --override-target is set, "; override=<id>"
            is appended. When --user-note is non-empty, it is appended too.

Pipe ``|`` and newlines inside text fields are stripped/replaced so the
appended entry stays parseable.

Exits 1 if the report lacks success_criterion or chosen_approach (run
validate_report.py first to catch shape issues earlier). Exits 2 on
malformed JSON. Exits 3 when the entry is already present (duplicate
fingerprint) — the row is skipped and "skipped (duplicate): ..." is printed.
Otherwise exits 0 and prints the appended entry summary to stdout.

CLI:
    cat runs/<file>.json | python scripts/log_feedback.py
    cat runs/<file>.json | python scripts/log_feedback.py
        --outcome OK --confirmed
    cat runs/<file>.json | python scripts/log_feedback.py --weak
    cat runs/<file>.json | python scripts/log_feedback.py --outcome OVR \\
        --override-target alt_b --user-note "preferred safer rollback"
    python scripts/log_feedback.py --feedback path/to/FEEDBACK.html
        < report.json
    python scripts/log_feedback.py --dry-run < report.json
"""
# implements: CONSILIUM-LOG-FEEDBACK-001

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path

from utils import (
    FEEDBACK_PATH,
    atomic_write_text,
    canonical_run_path,
    feedback_lock,
    force_utf8_streams,
    load_json_stdin,
)


CONTEXT_MAX = 60
NOTE_MAX = 80
HEADER_LINES = ()  # legacy MD header no longer used
RUN_PATH_MAP = ".run_path_map.json"
WEAK_MARKER = "[weak]"  # below-floor quality flag; the row stays PEND
CONFIRMED_MARKER = "[confirmed]"  # same marker mark_outcome.py writes;
# priors.py rates only these rows


def _fingerprint(
    date_str: str, chosen: str, context: str, run_id: str | None = None
) -> str:
    """16-char hex fingerprint for a feedback entry (used as sidecar
    map key).

    ``run_id`` is the basename of the run JSON file
    (e.g. ``2026-05-17_foo.json``).
    When provided it makes the fingerprint unique per run, preventing collisions
    between same-day entries with the same chosen+context prefix.  When absent
    (e.g. when recomputing fingerprints for rows already in FEEDBACK.html that
    were written without a run_id), we fall back to a microsecond-precision
    timestamp component so that two distinct logging calls on the same day
    cannot silently collide on the old 30-char context truncation.
    """
    disambiguator = run_id if run_id else datetime.now().strftime("%f")
    raw = f"{date_str}|{chosen}|{context}|{disambiguator}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _load_map(runs_dir: Path) -> dict[str, str]:
    map_path = runs_dir / RUN_PATH_MAP
    if not map_path.exists():
        return {}
    try:
        return json.loads(map_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_map(runs_dir: Path, run_map: dict[str, str]) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        runs_dir / RUN_PATH_MAP,
        json.dumps(run_map, indent=2, ensure_ascii=False),
    )


def _clean(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").replace("\r", " ").strip()


def truncate(text: str, n: int) -> str:
    text = _clean(text or "")
    if len(text) <= n:
        return text
    # leave room for the ellipsis
    return text[: max(0, n - 1)].rstrip() + "…"


def derive_note(report: dict) -> str:
    if report.get("skipped") is True:
        return truncate(f"skipped: {report.get('skip_reason', '')}", NOTE_MAX)

    log = report.get("deliberation_log") or []
    aggregate_step = next(
        (
            s for s in log
            if isinstance(s, dict) and s.get("step") == "aggregate"
        ),
        {},
    )
    raw_result = aggregate_step.get("result")
    # Manual-assembled runs may put a narrative string in `result` instead of
    # the canonical aggregate dict; coerce to {} so note derivation keeps going.
    aggregate_result = raw_result if isinstance(raw_result, dict) else {}

    chosen = report.get("chosen_approach")
    if chosen is None:
        relaxed = (aggregate_result.get("retry_suggested") or {}).get(
            "relaxed_threshold"
        )
        relaxed_s = (
            f"{relaxed:.2f}"
            if isinstance(relaxed, (int, float))
            and not isinstance(relaxed, bool)
            else "?"
        )
        return truncate(f"all vetoed; relaxed={relaxed_s}", NOTE_MAX)

    generator_step = next(
        (
            s for s in log
            if isinstance(s, dict) and s.get("step") == "generator"
        ),
        {},
    )
    n_cand = len(generator_step.get("candidates") or [])
    n_vetoed = len(aggregate_result.get("vetoed") or [])
    conf = report.get("confidence")
    conf_s = (
        f"{conf:.2f}"
        if isinstance(conf, (int, float)) and not isinstance(conf, bool)
        else "?"
    )
    mode = (report.get("telemetry") or {}).get("mode", "?")
    return truncate(
        f"{n_cand} cand, {n_vetoed} vetoed, conf={conf_s}, mode={mode}",
        NOTE_MAX,
    )


def build_entry(
    report: dict,
    outcome: str = "PEND",
    override_target: str | None = None,
    user_note: str | None = None,
    confirmed: bool = False,
    weak: bool = False,
) -> dict:
    sc = report.get("success_criterion")
    if not isinstance(sc, str) or not sc.strip():
        raise ValueError("report missing non-empty success_criterion")

    if "chosen_approach" not in report:
        raise ValueError("report missing chosen_approach")
    chosen = report["chosen_approach"]
    if chosen is None:
        chosen_s = "null"
    elif isinstance(chosen, str) and chosen.strip():
        chosen_s = _clean(chosen)
    else:
        raise ValueError("chosen_approach must be null or a non-empty string")

    if outcome == "OVR" and not override_target:
        raise ValueError("--outcome OVR requires --override-target <alt_id>")

    auto_note = derive_note(report)
    extras: list[str] = []
    if outcome == "OVR" and override_target:
        extras.append(f"override={_clean(override_target)}")
    if user_note and user_note.strip():
        extras.append(_clean(user_note))
    if confirmed:
        extras.append(CONFIRMED_MARKER)
    if weak:
        extras.append(WEAK_MARKER)
    note = "; ".join([auto_note] + extras) if extras else auto_note

    return {
        "date": date.today().isoformat(),
        "context": truncate(sc, CONTEXT_MAX),
        "chosen": chosen_s,
        "outcome": outcome,
        "note": note,
        "vote_pattern": _clean(report.get("vote_pattern") or ""),
    }


def _load_sibling(mod_name: str, filename: str):
    """Load a sibling script by path (importlib; scripts are not a package)."""
    import importlib.util
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(mod_name, here / filename)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _row_run_path(row: dict, run_map: dict[str, str]) -> str | None:
    """Restore run_path for an existing row from the sidecar map so
    drill-down survives re-renders. For each row, reconstruct its
    fingerprint using the run_id extracted from each known
    run_path; on a match the row's run_path is recovered. Rows
    logged without a run_id used an unstable timestamp and cannot
    be matched — they fall back to run_path=None (legacy
    behaviour)."""
    for fp, rp in run_map.items():
        run_id_candidate = Path(rp).name if rp else None
        fp_candidate = _fingerprint(
            row["date"], row["chosen"], row["context"],
            run_id=run_id_candidate,
        )
        if fp_candidate == fp:
            return rp
    return None


def _find_run_row(
    existing: list[dict], run_map: dict[str, str], run_path: str | None
) -> int | None:
    """Index of the existing row already mapped to ``run_path``, if any."""
    if not (run_path and run_path in run_map.values()):
        return None
    for i, row in enumerate(existing):
        if _row_run_path(row, run_map) == run_path:
            return i
    return None


def _stable_fp(row: dict) -> str:
    return hashlib.sha256(
        f"{row['date']}|{row['chosen']}|{row['context']}".encode()
    ).hexdigest()[:16]


def _find_unmapped_row(
    existing: list[dict], run_map: dict[str, str], entry: dict
) -> int | None:
    """Index of a row with this entry's content that no run is mapped to.

    That is the row an interrupted earlier call left behind: written, but
    the sidecar entry that would have claimed it was never saved. Adopting
    it on retry (instead of appending) keeps the retry from duplicating it.
    """
    want = _stable_fp(entry)
    for i, row in enumerate(existing):
        if _stable_fp(row) == want and _row_run_path(row, run_map) is None:
            return i
    return None


def _print_duplicate(new_fp: str) -> None:
    print(
        f"log_feedback: duplicate entry (fp {new_fp[:8]}) — "
        "already in FEEDBACK.html, skipping append.",
        file=sys.stderr,
    )


def _existing_entries(
    existing: list[dict], run_map: dict[str, str], render_mod
) -> list:
    return [
        render_mod.Entry(**row, run_path=_row_run_path(row, run_map))
        for row in existing
    ]


def _upgrade_entries(
    existing: list[dict],
    matched_idx: int,
    entry: dict,
    run_map: dict[str, str],
    render_mod,
) -> list:
    """Outcome update (PEND -> OK/BAD/OVR): patch the matched row with the
    new outcome/note (and vote_pattern when given) and return the full
    re-render list."""
    prior = existing[matched_idx]
    prior["outcome"] = entry["outcome"]
    prior["note"] = entry["note"]
    if entry.get("vote_pattern"):
        prior["vote_pattern"] = entry["vote_pattern"]
    return _existing_entries(existing, run_map, render_mod)


def _append_entry_locked(
    feedback_path: Path, entry: dict, run_path: str | None
) -> int:
    """Round-trip the HTML: parse existing rows, append, re-render.

    Returns:
        0  — new row written successfully.
        3  — duplicate fingerprint detected; row skipped (caller should exit 3
             so the caller can distinguish "duplicate" from "success").

    Callers can use the return value to track how many real appends happened —
    important for audit_feedback's --backfill summary.
    """
    feedback_mod = _load_sibling("consilium_feedback", "feedback.py")
    render_mod = _load_sibling("consilium_render", "render_feedback_html.py")

    existing = feedback_mod.parse_feedback(feedback_path)
    runs_dir = feedback_path.parent / "runs"
    run_map = _load_map(runs_dir)

    run_id = Path(run_path).name if run_path else None
    new_fp = _fingerprint(
        entry["date"], entry["chosen"], entry["context"], run_id=run_id
    )

    # Close-the-loop: when run_path already has a row, distinguish a true
    # duplicate (same outcome — skip) from an outcome update (PEND -> OK/BAD/OVR
    # — upgrade the row in place). The old blanket "run_path seen => duplicate"
    # swallowed Step-6 close-the-loop calls, leaving PEND rows un-upgraded.
    matched_idx = _find_run_row(existing, run_map, run_path)
    if matched_idx is None and run_path:
        matched_idx = _find_unmapped_row(existing, run_map, entry)
    if matched_idx is not None:
        assert run_path  # matched_idx is only set when run_path is truthy
        prior = existing[matched_idx]
        if prior.get("outcome") == entry["outcome"]:
            _print_duplicate(new_fp)
            run_map[new_fp] = run_path
            _save_map(runs_dir, run_map)
            return 3
        entries = _upgrade_entries(existing, matched_idx, entry, run_map,
                                   render_mod)
        # Row first, sidecar second: a crash between the two leaves a row
        # the next call adopts, never a sidecar entry claiming a missing row.
        atomic_write_text(
            feedback_path, render_mod.render(entries, runs_dir)
        )
        run_map[new_fp] = run_path
        _save_map(runs_dir, run_map)
        print(
            f"log_feedback: upgraded {prior['chosen']} -> "
            f"{entry['outcome']} in place (run {run_id}).",
            file=sys.stderr,
        )
        return 0

    # Content-only duplicate check for rows logged WITHOUT a run_path:
    # same date+chosen+full-context means the same entry (no
    # timestamp component).
    if not run_path and _stable_fp(entry) in {
        _stable_fp(row) for row in existing
    }:
        _print_duplicate(new_fp)
        return 3

    entries = _existing_entries(existing, run_map, render_mod)
    entries.append(render_mod.Entry(
        date=entry["date"],
        context=entry["context"],
        chosen=entry["chosen"],
        outcome=entry["outcome"],
        note=entry["note"],
        run_path=run_path,
        vote_pattern=entry.get("vote_pattern", ""),
    ))

    atomic_write_text(feedback_path, render_mod.render(entries, runs_dir))

    # Persist run_path for the new entry so future re-renders can
    # recover it — after the row, see the upgrade branch above.
    if run_path:
        run_map[new_fp] = run_path
        _save_map(runs_dir, run_map)
    return 0


def append_entry(
    feedback_path: Path, entry: dict, run_path: str | None
) -> int:
    """``_append_entry_locked`` under ``feedback_lock``: the parse, the
    row write and the sidecar write are one transaction."""
    with feedback_lock(feedback_path):
        return _append_entry_locked(feedback_path, entry, run_path)


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--feedback",
        default=None,
        help="path to FEEDBACK.html (default: .consilium/FEEDBACK.html)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="print summary, don't write file",
    )
    ap.add_argument(
        "--outcome",
        choices=("OK", "BAD", "OVR", "PEND", "PEND_HEADLESS"),
        default="PEND",
        help=(
            "outcome to record (default: PEND; set OK/OVR after "
            "confidence-gated user prompt; use PEND_HEADLESS in "
            "headless/CI context to avoid polluting pend_pressure)"
        ),
    )
    ap.add_argument(
        "--override-target", default=None,
        help="alt_id when --outcome=OVR",
    )
    ap.add_argument(
        "--user-note", default=None,
        help="optional user-supplied note appended to auto-note",
    )
    ap.add_argument(
        "--run-path", default=None,
        help=(
            "relative path to runs/*.json for drill-down "
            "(e.g. runs/2026-05-12_foo.json)"
        ),
    )
    ap.add_argument(
        "--force-override", action="store_true",
        help=(
            "allow --outcome OK even when confidence < 0.70 (use "
            "when user has confirmed the pick despite low confidence)"
        ),
    )
    ap.add_argument(
        "--weak", action="store_true",
        help=(
            "the run fell below its mode confidence floor "
            "(check_mode_floor); adds the [weak] note marker. Advisory "
            "quality metadata, not an outcome — the row stays PEND"
        ),
    )
    ap.add_argument(
        "--confirmed", action="store_true",
        help=(
            "the outcome was verified (the verification command "
            "passed, or the user confirmed it worked); "
            "required for --outcome OK; adds the [confirmed] marker"
        ),
    )
    return ap


def _check_ok_gate(args: argparse.Namespace, report: dict) -> int | None:
    """Guards for --outcome OK; returns an exit code, or None to proceed."""
    if args.outcome == "OK" and not args.confirmed:
        print(
            "log_feedback: --outcome OK is a verified outcome — pass "
            "--confirmed once the verification passed; otherwise log "
            "PEND (default) and close it later with mark_outcome.py",
            file=sys.stderr,
        )
        return 1

    if args.outcome == "OK":
        conf = report.get("confidence")
        below = conf is None or (
            isinstance(conf, (int, float))
            and not isinstance(conf, bool)
            and conf < 0.7
        )
        if below and not args.force_override:
            conf_s = (
                f"{conf:.2f}"
                if isinstance(conf, (int, float))
                and not isinstance(conf, bool)
                else str(conf)
            )
            print(
                f"confidence {conf_s} is below threshold 0.70 — "
                "pass --force-override to log OK despite low confidence",
                file=sys.stderr,
            )
            return 1
    return None


def _entry_line(entry: dict) -> str:
    return (
        f"{entry['date']} | {entry['context']} | {entry['chosen']} | "
        f"{entry['outcome']} | {entry['note']}"
    )


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    args = _build_parser().parse_args(argv)

    if args.outcome == "OVR" and not args.override_target:
        print(
            "log_feedback: --outcome OVR requires "
            "--override-target <alt_id>",
            file=sys.stderr,
        )
        sys.exit(2)

    report = load_json_stdin("log_feedback.py")
    if not isinstance(report, dict):
        print("log_feedback.py: report must be a JSON object", file=sys.stderr)
        return 2

    gate_rc = _check_ok_gate(args, report)
    if gate_rc is not None:
        return gate_rc

    try:
        entry = build_entry(
            report,
            outcome=args.outcome,
            override_target=args.override_target,
            user_note=args.user_note,
            confirmed=args.confirmed,
            weak=args.weak,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not args.dry_run:
        feedback_path = (
            Path(args.feedback) if args.feedback else FEEDBACK_PATH
        )
        run_path = (
            canonical_run_path(args.run_path) if args.run_path else None
        )
        rc = append_entry(feedback_path, entry, run_path)
        if rc != 0:
            # Exit 3 means duplicate detected — prefix the line so
            # callers parsing stdout can distinguish "duplicate
            # skipped" from a real "success" write.
            print(f"skipped (duplicate): {_entry_line(entry)}")
            return rc

    print(_entry_line(entry))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
