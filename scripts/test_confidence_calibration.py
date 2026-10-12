#!/usr/bin/env python
"""Smoke tests for confidence_calibration.py.

Stdlib-only, no test runner — run directly:
    python scripts/test_confidence_calibration.py

Tests the pure logic (records -> bins -> verdict) on synthetic entry lists,
plus the HTML path end-to-end via a temp FEEDBACK file.
"""
# tested-by: CONSILIUM-CONFIDENCE-CALIBRATION-001
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_spec = importlib.util.spec_from_file_location(
    "confidence_calibration", _SCRIPTS / "confidence_calibration.py")
assert _spec and _spec.loader
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

_fails: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fails.append(name)


def entry(conf: float | None, outcome: str) -> dict:
    note = f"5 cand, 0 vetoed, conf={conf}, mode=sequential" if conf is not None else "no conf here"
    return {"date": "2026-01-01", "context": "x", "chosen": "y", "outcome": outcome, "note": note}


def test_records_filter() -> None:
    entries = [
        entry(0.9, "OK"),            # kept -> (0.9, 1)
        entry(0.4, "BAD"),           # kept -> (0.4, 0)
        entry(0.8, "OVR"),           # kept -> (0.8, 0)  OVR = failure
        entry(0.95, "PEND"),         # dropped — unresolved
        entry(0.5, "PEND_HEADLESS"), # dropped — unresolved
        entry(None, "OK"),           # dropped — no conf in note
    ]
    recs = cc.calibration_records(entries)
    check("records: keeps only resolved AND conf-tagged", len(recs) == 3)
    check("records: OVR mapped to failure", (0.8, 0) in recs)
    check("records: OK mapped to success", (0.9, 1) in recs)


def test_note_without_conf_skipped() -> None:
    recs = cc.calibration_records([entry(None, "OK"), entry(None, "BAD")])
    check("note without conf= is skipped", recs == [])


def _decide(records):
    return cc.decide(records, cc.Thresholds(
        gate=0.7, margin=0.15, min_resolved=20, min_negatives=10,
        min_band=5, high_floor=0.75))


def test_sharp_ship_c() -> None:
    # High band almost all OK; low band mostly BAD. Plenty of negatives.
    records = [(0.9, 1)] * 25 + [(0.85, 1)] * 5 + [(0.4, 0)] * 15 + [(0.5, 1)] * 5
    d = _decide(records)
    check("sharp corpus -> SHIP_C", d["verdict"] == "SHIP_C")
    check("sharp: discrimination >= margin", d["discrimination"] >= 0.15)


def test_flat_fallback_a() -> None:
    # Same OK-rate (~0.7) in both bands -> no discrimination.
    records = ([(0.9, 1)] * 14 + [(0.9, 0)] * 6) + ([(0.4, 1)] * 14 + [(0.4, 0)] * 6)
    d = _decide(records)
    check("flat corpus -> FALLBACK_A", d["verdict"] == "FALLBACK_A")


def test_insufficient_data() -> None:
    # Only a handful of resolved, few negatives.
    records = [(0.9, 1)] * 8 + [(0.4, 0)] * 2
    d = _decide(records)
    check("tiny corpus -> INSUFFICIENT_DATA", d["verdict"] == "INSUFFICIENT_DATA")


def test_insufficient_when_no_negatives() -> None:
    # OK-dominated (like the real corpus): plenty resolved but too few negatives.
    records = [(0.9, 1)] * 200 + [(0.4, 0)] * 3
    d = _decide(records)
    check("OK-dominated corpus -> INSUFFICIENT_DATA (too few negatives)",
          d["verdict"] == "INSUFFICIENT_DATA")


def test_bins() -> None:
    records = [(0.95, 1), (0.65, 0), (0.05, 1)]
    bins = cc.compute_bins(records, cc.DEFAULT_EDGES)
    top = bins[-1]
    check("bins: conf=1.0 region holds the 0.95 entry", top["n"] == 1 and top["ok"] == 1)
    check("bins: empty bin has ok_rate None", any(b["n"] == 0 and b["ok_rate"] is None for b in bins))


def test_html_end_to_end() -> None:
    # Minimal FEEDBACK.html the canonical parser accepts.
    rows = []
    for conf, outcome in [(0.9, "OK")] * 25 + [(0.4, "BAD")] * 12 + [(0.5, "OK")] * 8:
        # Legacy 6-cell layout: [chevron, date, context, chosen, outcome, note].
        rows.append(
            '<tr class="entry">'
            "<td>+</td><td>2026-01-01</td><td>ctx</td><td>cand</td>"
            f"<td>{outcome}</td>"
            f"<td>5 cand, 0 vetoed, conf={conf}, mode=sequential</td>"
            "</tr>"
        )
    html = "<table>\n" + "\n".join(rows) + "\n</table>"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "FEEDBACK.html"
        p.write_text(html, encoding="utf-8")
        result = cc.run(p, cc.Thresholds(
            gate=0.7, margin=0.15, min_resolved=20, min_negatives=10,
            min_band=5, high_floor=0.75), cc.DEFAULT_EDGES)
    check("html end-to-end: parses resolved rows", result["resolved"] == 45)
    check("html end-to-end: produces a verdict", result["verdict"] in
          {"SHIP_C", "FALLBACK_A", "INSUFFICIENT_DATA"})


def main() -> int:
    print("test_confidence_calibration")
    for fn in [test_records_filter, test_note_without_conf_skipped, test_sharp_ship_c,
               test_flat_fallback_a, test_insufficient_data, test_insufficient_when_no_negatives,
               test_bins, test_html_end_to_end]:
        fn()
    print(f"\n{'OK' if not _fails else 'FAILED: ' + ', '.join(_fails)}")
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
