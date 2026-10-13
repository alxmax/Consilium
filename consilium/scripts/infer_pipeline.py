"""Infer and confirm implementation pipeline steps from a Consilium
deliberation report.

Reads a deliberation JSON (produced by build_report.py), infers which
implementation steps apply based on chosen_approach, magnitude, and
reversibility, then presents them for confirmation before execution.

Usage:
    cat runs/<file>.json | python scripts/infer_pipeline.py
    python scripts/infer_pipeline.py --input runs/<file>.json
    python scripts/infer_pipeline.py --input runs/<file>.json --dry-run
    python scripts/infer_pipeline.py --input runs/<file>.json --yes

Flags:
    --dry-run   Print inferred steps and exit without confirmation or execution.
    --yes       Skip confirmation prompt (CI/headless mode).
    --debug     Emit decision rationale to stderr (source, lookup key,
                fallback path).

Steps (in order when applicable):
    implement   Write code per chosen_approach (reminder — not automated).
    compile     Run the target module; verify exit code 0 (runtime check).
    review      Re-run Control voice on the actual written code.
    test        Run existing test suite (pytest/unittest autodiscovery).

Exit codes:
    0   Steps confirmed and printed to stdout, or dry-run complete.
    1   User declined, or step inference produced no steps.
    2   Input invalid (JSON parse error or missing required fields).
"""
# implements: CONSILIUM-INFER-PIPELINE-001

from __future__ import annotations

import argparse
import datetime
import json
import sys

from utils import RUNS_DIR, force_utf8_streams

# Lookup table: (magnitude, reversibility) -> ordered step list.
# Conservative tie-breaking: most restrictive key wins (see _infer_steps).
_STEP_TABLE: dict[tuple[str, str], list[str]] = {
    ("trivial",  "complete"):    ["implement"],
    ("trivial",  "partial"):     ["implement", "compile"],
    ("trivial",  "irreversible"):["implement", "compile", "test"],
    ("moderate", "complete"):    ["implement", "compile"],
    ("moderate", "partial"):     ["implement", "compile", "test"],
    ("moderate", "irreversible"):["implement", "compile", "review", "test"],
    ("high",     "complete"):    ["implement", "compile", "test"],
    ("high",     "partial"):     ["implement", "compile", "review", "test"],
    ("high",     "irreversible"):["implement", "compile", "review", "test"],
    ("critical", "complete"):    ["implement", "compile", "review", "test"],
    ("critical", "partial"):     ["implement", "compile", "review", "test"],
    ("critical", "irreversible"):["implement", "compile", "review", "test"],
}

# Fallback magnitude tiers when conservator fields are missing from the report.
# net_concern is floored UP to >=0.9 when a candidate is irreversible
# (conservator.md net_concern formula), so it is a magnitude PROXY only — the
# reversibility axis is handled separately in _fallback_from_concern, never
# inferred from this scalar.
_MAGNITUDE_BUCKETS = [
    (0.0,  0.15, "trivial"),
    (0.15, 0.35, "moderate"),
    (0.35, 0.65, "high"),
    (0.65, 1.01, "critical"),
]

# Valid conservator vocabularies. Any off-vocabulary token (e.g. an emitted
# "none") is treated as missing so it routes through the net_concern fallback
# instead of falsely defaulting to the full step set + 'pipeline'.
_VALID_MAGNITUDES = frozenset({"trivial", "moderate", "high", "critical"})
_VALID_REVERSIBILITY = frozenset({"complete", "partial", "irreversible"})


def _extract_conservator_fields(
    report: dict, chosen: str
) -> tuple[str | None, str | None]:
    """Return (magnitude, reversibility) for chosen from deliberation_log."""
    for entry in report.get("deliberation_log", []):
        if entry.get("step") != "conservator":
            continue
        for score in entry.get("scores", []):
            if score.get("id") == chosen:
                rr = score.get("regression_risk", {})
                return rr.get("magnitude"), rr.get("reversibility")
    return None, None


def _fallback_from_concern(
    net_concern: float, reversibility: str | None = None
) -> tuple[str, str]:
    """Reconstruct (magnitude, reversibility) from a scalar net_concern.

    Separates the two axes. net_concern maps to a magnitude tier; reversibility
    is taken from the caller when the report already provided a valid value, and
    otherwise defaults to the conservative-but-bounded 'partial'. We never infer
    'irreversible' from the scalar: net_concern is floored up to >=0.9 for
    irreversible candidates, so a high value is ambiguous between 'genuinely
    critical' and 'merely irreversible' — guessing 'irreversible' would
    over-route trivial-but-irreversible changes into the review quadrant.
    """
    rev = reversibility if reversibility in _VALID_REVERSIBILITY else "partial"
    for lo, hi, mag in _MAGNITUDE_BUCKETS:
        if lo <= net_concern < hi:
            return mag, rev
    return "critical", rev


def infer_steps(report: dict) -> tuple[list[str], dict]:
    """Return (steps, rationale) from a deliberation report."""
    chosen = report.get("chosen_approach")

    if chosen in ("do_nothing", "skipped", None, ""):
        return [], {"reason": f"chosen_approach={chosen!r} — no steps to run"}

    magnitude, reversibility = _extract_conservator_fields(report, chosen)
    source = "deliberation_log"

    mag_valid = magnitude in _VALID_MAGNITUDES
    rev_valid = reversibility in _VALID_REVERSIBILITY
    if not (mag_valid and rev_valid):
        # `voice_scores` is explicitly null on hand-built reports
        # (prior-deliberation passthrough, scale_down trivial-direct), so
        # `.get("voice_scores", {})` returns None — guard with `or {}` before
        # the nested .get to avoid AttributeError.
        # `or 0.5` would coerce a legitimate 0.0 to 0.5 — only None means
        # missing.
        _raw_concern = (report.get("voice_scores") or {}).get("conservator")
        net_concern = 0.5 if _raw_concern is None else float(_raw_concern)
        fb_mag, fb_rev = _fallback_from_concern(
            net_concern, reversibility if rev_valid else None
        )
        # Keep whichever axis the report actually provided; reconstruct only
        # the missing one. A known reversibility sidesteps the
        # floored-scalar ambiguity for that axis (e.g. a known 'complete'
        # avoids a spurious review step).
        magnitude = magnitude if mag_valid else fb_mag
        reversibility = reversibility if rev_valid else fb_rev
        missing = " + ".join(
            a for a, ok in (
                ("magnitude", mag_valid), ("reversibility", rev_valid)
            ) if not ok
        )
        source = (
            f"voice_scores.conservator={net_concern} "
            f"(fallback; reconstructed {missing})"
        )

    key = (magnitude, reversibility)
    steps = _STEP_TABLE.get(key)

    if steps is None:
        # Key not in table: default to safest full set.
        steps = ["implement", "compile", "review", "test"]
        source += " (key not in table — defaulting to full set)"

    rationale = {
        "chosen": chosen,
        "magnitude": magnitude,
        "reversibility": reversibility,
        "source": source,
        "lookup_key": f"({magnitude}, {reversibility})",
    }
    return list(steps), rationale


def recommend_implement_mode(report: dict) -> str:
    """Route the Step 7 `implement` action: ``"pipeline"`` vs ``"single_shot"``.

    Gate keyed on **regression risk, not size** (benchmark
    `experiments/pipeline-bench/`: the pipeline's only win was a 3-line edit
    to existing code — a size threshold would have mis-routed it). The
    signal reused here is the `review` step from ``infer_steps``: it appears
    exactly in the regression-prone quadrants (moderate×irreversible,
    high×{partial,irreversible}, critical×any). When `review` is warranted,
    the change is worth the pipeline (Coder → Test Writer ∥ Reviewer);
    otherwise plain single-shot.

    Advisory only — the orchestrator/user may override. Returns
    ``"single_shot"`` for ``do_nothing``/``skipped`` (no implementation to
    route).
    """
    steps, _ = infer_steps(report)
    return "pipeline" if "review" in steps else "single_shot"


def _log_rejection(report: dict, steps: list[str], rationale: dict) -> None:
    runs_dir = RUNS_DIR
    if not runs_dir.exists():
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    entry = {
        "event": "pipeline_rejected",
        "timestamp": timestamp,
        "steps_proposed": steps,
        "rationale": rationale,
        "success_criterion": report.get("success_criterion", ""),
        "chosen_approach": report.get("chosen_approach", ""),
    }
    path = runs_dir / f"{timestamp}_pipeline_rejected.json"
    path.write_text(
        json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _load_report(input_path: str | None) -> dict:
    """Read the deliberation JSON from --input or stdin; exit 2 on error."""
    try:
        if input_path:
            with open(input_path, encoding="utf-8") as f:
                return json.load(f)
        raw = sys.stdin.read()
        if not raw.strip():
            print(
                "infer_pipeline: no input — pipe a deliberation JSON "
                "or use --input",
                file=sys.stderr,
            )
            sys.exit(2)
        return json.loads(raw)
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        print(f"infer_pipeline: input error: {exc}", file=sys.stderr)
        sys.exit(2)


def _confirm_or_exit(report: dict, steps: list[str], rationale: dict) -> None:
    """Prompt to proceed; exit 1 when declined or non-interactive."""
    try:
        answer = input("\nProceed? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print(
            "\ninfer_pipeline: non-interactive environment detected — "
            "rerun with --yes to skip prompt",
            file=sys.stderr,
        )
        sys.exit(1)
    if answer not in ("", "y", "yes"):
        print("infer_pipeline: declined")
        _log_rejection(report, steps, rationale)
        sys.exit(1)


def main() -> None:
    force_utf8_streams()

    parser = argparse.ArgumentParser(
        description=(
            "Infer and confirm pipeline steps from a Consilium "
            "deliberation report."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input",
                        help="Path to deliberation JSON (default: stdin)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print steps and exit without confirmation")
    parser.add_argument("--yes", action="store_true",
                        help="Skip confirmation prompt (CI/headless mode)")
    parser.add_argument("--debug", action="store_true",
                        help="Emit decision rationale to stderr")
    args = parser.parse_args()

    report = _load_report(args.input)

    steps, rationale = infer_steps(report)

    if args.debug:
        print(f"[debug] chosen={rationale.get('chosen')!r}", file=sys.stderr)
        print(f"[debug] source={rationale.get('source')!r}", file=sys.stderr)
        print(f"[debug] lookup_key={rationale.get('lookup_key')!r}",
              file=sys.stderr)
        print(f"[debug] steps={steps!r}", file=sys.stderr)

    if not steps:
        reason = rationale.get("reason", "unknown")
        print(f"infer_pipeline: no steps — {reason}")
        print(json.dumps(
            {"steps": [], "rationale": rationale}, ensure_ascii=False
        ))
        sys.exit(1)

    pipeline_str = " → ".join(steps)
    print(f"\nProposed pipeline: {pipeline_str}")
    print(f"  chosen : {rationale['chosen']}")
    print(f"  profile: {rationale['lookup_key']} "
          f"(source: {rationale['source']})")

    if args.dry_run:
        print("(dry-run — no confirmation)")
        print(json.dumps(
            {"steps": steps, "rationale": rationale}, ensure_ascii=False
        ))
        sys.exit(0)

    if not args.yes:
        _confirm_or_exit(report, steps, rationale)

    print(json.dumps(
        {"steps": steps, "rationale": rationale}, ensure_ascii=False
    ))
    sys.exit(0)


if __name__ == "__main__":
    main()
