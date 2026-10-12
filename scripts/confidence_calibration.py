#!/usr/bin/env python
"""Confidence-calibration gate for Variant C (confidence-gated Trias).

review ranking (an internal design audit + the variant-ranking round)
made Variant C conditional on ONE cheap check: do high confidence scores
actually predict OK outcomes in the existing corpus? If yes, C's gate
(skeptic fires only when ``confidence in [0.0, 0.70)`` — strictly below 0.70)
is justified — ship C.
If not, the gate is illusory — fall back to Variant A (always one skeptic).

This script answers that, with zero new deliberation runs. It reads the
resolved outcomes already logged in ``.consilium/FEEDBACK.html`` (each row
embeds ``conf=<x>`` in its note), buckets them by confidence, and reports the
OK-rate per bin plus a verdict:

    SHIP_C            high-confidence runs reliably beat low-confidence runs
                      (discrimination >= --margin AND high-band OK-rate high)
    FALLBACK_A        confidence does not discriminate -> gate is illusory
    INSUFFICIENT_DATA too few resolved outcomes, or too few negatives, to tell

Reuse: ``parse_feedback`` from ``feedback.py`` (same importlib pattern as
``priors.py``) — one source of truth for the FEEDBACK row format.

Usage:
    python scripts/confidence_calibration.py
    python scripts/confidence_calibration.py --gate 0.7 --margin 0.15 --json
    python scripts/confidence_calibration.py --feedback path/to/FEEDBACK.html
"""
# implements: CONSILIUM-CONFIDENCE-CALIBRATION-001
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from utils import (  # noqa: E402 — scripts/ on path
    FEEDBACK_PATH,
    force_utf8_streams,
)

# Reuse the canonical FEEDBACK parser (same importlib approach as priors.py).
_FB_PATH = _SCRIPTS / "feedback.py"
_spec = importlib.util.spec_from_file_location("consilium_feedback", _FB_PATH)
assert _spec and _spec.loader
_feedback = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_feedback)
parse_feedback = _feedback.parse_feedback

CONF_RE = re.compile(r"conf=([0-9]*\.?[0-9]+)")

# Outcome -> success(1) / failure(0) / None(unresolved, excluded from
# calibration).
SUCCESS = {"OK"}
# OVR = the chosen was overridden -> confidence was misplaced.
FAILURE = {"BAD", "OVR"}

# 1.01 so conf==1.0 lands in the top bin.
DEFAULT_EDGES = [0.0, 0.6, 0.7, 0.8, 0.9, 1.01]


def calibration_records(entries: list[dict]) -> list[tuple[float, int]]:
    """(confidence, success) pairs for entries that are BOTH resolved and
    conf-tagged."""
    records: list[tuple[float, int]] = []
    for e in entries:
        outcome = e.get("outcome", "")
        if outcome in SUCCESS:
            success = 1
        elif outcome in FAILURE:
            success = 0
        else:
            continue  # PEND / PEND_HEADLESS / WEAK / "" — not yet knowable.
        m = CONF_RE.search(e.get("note", ""))
        if not m:
            continue
        conf = float(m.group(1))
        if not 0.0 <= conf <= 1.0:
            continue
        records.append((conf, success))
    return records


def compute_bins(
    records: list[tuple[float, int]], edges: list[float]
) -> list[dict]:
    """Per-bin {lo, hi, n, ok, ok_rate} over the half-open bins
    [edges[i], edges[i+1])."""
    bins = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        members = [s for c, s in records if lo <= c < hi]
        n = len(members)
        ok = sum(members)
        bins.append({"lo": lo, "hi": min(hi, 1.0), "n": n, "ok": ok,
                     "ok_rate": (ok / n) if n else None})
    return bins


def band_rate(
    records: list[tuple[float, int]], gate: float, high: bool
) -> tuple[int, float | None]:
    members = [s for c, s in records if (c >= gate) == high]
    n = len(members)
    return n, (sum(members) / n if n else None)


class Thresholds(NamedTuple):
    """The gate's tunables — they always travel together."""
    gate: float
    margin: float
    min_resolved: int
    min_negatives: int
    min_band: int
    high_floor: float


def decide(records: list[tuple[float, int]], t: Thresholds) -> dict:
    gate, margin, high_floor = t.gate, t.margin, t.high_floor
    min_resolved, min_negatives = t.min_resolved, t.min_negatives
    min_band = t.min_band
    resolved = len(records)
    negatives = sum(1 for _, s in records if s == 0)
    low_n, low_rate = band_rate(records, gate, high=False)
    high_n, high_rate = band_rate(records, gate, high=True)

    detail = {
        "resolved": resolved, "negatives": negatives,
        "low_band": {"n": low_n, "ok_rate": low_rate},
        "high_band": {"n": high_n, "ok_rate": high_rate},
        "gate": gate, "margin": margin, "high_floor": high_floor,
    }

    if (resolved < min_resolved or negatives < min_negatives
            or low_n < min_band or high_n < min_band):
        detail["verdict"] = "INSUFFICIENT_DATA"
        reasons = []
        if resolved < min_resolved:
            reasons.append(f"resolved {resolved} < {min_resolved}")
        if negatives < min_negatives:
            reasons.append(f"negatives {negatives} < {min_negatives}")
        if low_n < min_band:
            reasons.append(f"low-band n {low_n} < {min_band}")
        if high_n < min_band:
            reasons.append(f"high-band n {high_n} < {min_band}")
        detail["reason"] = "; ".join(reasons)
        detail["discrimination"] = None
        return detail

    discrimination = high_rate - low_rate  # type: ignore[operator]
    detail["discrimination"] = discrimination
    if (discrimination >= margin
            and high_rate >= high_floor):  # type: ignore[operator]
        detail["verdict"] = "SHIP_C"
        detail["reason"] = (f"high-band OK-rate {high_rate:.2f} beats low-band "
                            f"{low_rate:.2f} by {discrimination:.2f} (>= "
                            f"{margin}) "
                            f"and clears the floor {high_floor}")
    else:
        detail["verdict"] = "FALLBACK_A"
        detail["reason"] = (
            f"confidence does not discriminate: high-band {high_rate:.2f} "
            f"vs low-band {low_rate:.2f} (delta {discrimination:.2f} < "
            f"{margin}) "
            f"or below floor {high_floor}")
    return detail


def render(bins: list[dict], decision: dict) -> str:
    out = ["confidence-calibration gate  (Variant C)", ""]
    out.append(f"  {'bin':>12}   {'n':>4}   {'ok':>4}   ok-rate")
    out.append("  " + "-" * 38)
    for b in bins:
        rate = "   -  " if b["ok_rate"] is None else f"{b['ok_rate']:.2f}"
        out.append(f"  [{b['lo']:.2f}, {b['hi']:.2f})   "
                    f"{b['n']:>4}   {b['ok']:>4}    {rate}")
    out.append("")
    lo, hi = decision["low_band"], decision["high_band"]
    lo_r = "-" if lo["ok_rate"] is None else f"{lo['ok_rate']:.2f}"
    hi_r = "-" if hi["ok_rate"] is None else f"{hi['ok_rate']:.2f}"
    out.append(
        f"  low band  (conf <  {decision['gate']}): n={lo['n']:>4}  "
        f"ok-rate={lo_r}"
    )
    out.append(
        f"  high band (conf >= {decision['gate']}): n={hi['n']:>4}  "
        f"ok-rate={hi_r}"
    )
    out.append(
        f"  resolved={decision['resolved']}  "
        f"negatives={decision['negatives']}"
    )
    out.append("")
    out.append(f"  VERDICT: {decision['verdict']}")
    out.append(f"  {decision['reason']}")
    return "\n".join(out)


def run(feedback_path: Path, t: Thresholds, edges: list[float]) -> dict:
    entries = parse_feedback(feedback_path)
    records = calibration_records(entries)
    bins = compute_bins(records, edges)
    decision = decide(records, t)
    return {"feedback_total": len(entries), "bins": bins, **decision}


def main() -> int:
    force_utf8_streams()
    ap = argparse.ArgumentParser(
        description="Confidence-calibration gate for Variant C."
    )
    ap.add_argument(
        "--feedback", type=Path, default=FEEDBACK_PATH,
        help="path to FEEDBACK.html (default: .consilium/FEEDBACK.html)",
    )
    ap.add_argument(
        "--gate", type=float, default=0.7,
        help="band split / C's gate threshold",
    )
    ap.add_argument(
        "--margin", type=float, default=0.15,
        help="min high-minus-low OK-rate gap to justify SHIP_C",
    )
    ap.add_argument(
        "--high-floor", type=float, default=0.75,
        help="min high-band OK-rate required for SHIP_C",
    )
    ap.add_argument("--min-resolved", type=int, default=20)
    ap.add_argument("--min-negatives", type=int, default=10)
    ap.add_argument("--min-band", type=int, default=5)
    ap.add_argument(
        "--json", action="store_true", help="emit JSON instead of a table"
    )
    args = ap.parse_args()

    if not args.feedback.exists():
        print(
            f"error: feedback file not found: {args.feedback}",
            file=sys.stderr,
        )
        return 2

    result = run(
        args.feedback,
        Thresholds(
            gate=args.gate, margin=args.margin,
            min_resolved=args.min_resolved,
            min_negatives=args.min_negatives,
            min_band=args.min_band, high_floor=args.high_floor,
        ),
        DEFAULT_EDGES,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render(result["bins"], result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
