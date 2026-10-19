"""Summarize feedback from FEEDBACK.html and runs/*.json.

Reads the journal at FEEDBACK.html, parses entries, and prints a short stats
report so you can see whether each voice (Generator, Control, Conservator)
is actually pulling its weight in your real-world uses.

CLI:
    python scripts/feedback.py             # stats on everything
    python scripts/feedback.py --recent 10 # last 10 entries only
    python scripts/feedback.py --runs      # also scan runs/*.json
"""
# implements: CONSILIUM-FEEDBACK-001

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# Loaded via importlib from several entry points (priors, log_feedback,
# mark_outcome, audit_feedback), so scripts/ may not be on sys.path.
# Bootstrap it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import FEEDBACK_PATH, RUNS_DIR

ROOT = Path(__file__).resolve().parent.parent
FEEDBACK = FEEDBACK_PATH
RUNS = RUNS_DIR

# CLOSED_UNVERIFIED: a PEND closed without evidence either way (stale cleanup,
# external project) — kept out of every rate, like PEND.
OUTCOMES = ("OK", "BAD", "OVR", "PEND", "PEND_HEADLESS", "CLOSED_UNVERIFIED")

ROW_RE = re.compile(
    r'<tr[^>]*class="entry"[^>]*>(?P<body>.*?)</tr>',
    re.DOTALL | re.IGNORECASE,
)
CELL_RE = re.compile(r'<td(?P<attrs>[^>]*)>(?P<text>.*?)</td>', re.DOTALL)
FIELD_ATTR_RE = re.compile(r'data-field="([^"]+)"')
TAG_RE = re.compile(r'<[^>]+>')


def _strip_tags(s: str) -> str:
    s = TAG_RE.sub('', s)
    # html.unescape is in the stdlib; avoids extra deps.
    import html as _html
    return _html.unescape(s).strip()


# Legacy positional layouts (rows without data-field attrs), keyed by cell
# count; values are cell indices for (date, context, chosen, outcome, note,
# vote_pattern), None = absent.
# Trias layout (8 cells): [chev, date, context, chosen, outcome, tokens,
# note, vote_pattern]
# Previous layout (7 cells): [chev, date, context, chosen, outcome, tokens,
# note]
# Legacy layout (6 cells): [chev, date, context, chosen, outcome, note]
# The tokens cell is regenerated at render time from run telemetry, so it
# is dropped here — the parser only returns the persistent fields.
_ROW_FIELDS = ("date", "context", "chosen", "outcome", "note", "vote_pattern")
_LEGACY_LAYOUTS = {
    8: (1, 2, 3, 4, 6, 7),
    7: (1, 2, 3, 4, 6, None),
    6: (1, 2, 3, 4, 5, None),
}


def _fields_from_attrs(cell_matches: list) -> dict[str, str]:
    """Attribute-based parsing (preferred, order-independent): rows written
    by render_feedback_html.py carry data-field="<name>" on each <td>."""
    field_map: dict[str, str] = {}
    for cm in cell_matches:
        fa = FIELD_ATTR_RE.search(cm.group("attrs"))
        if fa:
            field_map[fa.group(1)] = _strip_tags(cm.group("text"))
    return field_map


def _fields_from_legacy(cell_matches: list) -> dict[str, str] | None:
    """Legacy positional fallback; None when the cell count is unknown."""
    layout = _LEGACY_LAYOUTS.get(len(cell_matches))
    if layout is None:
        return None
    cells = [cm.group("text") for cm in cell_matches]
    return {
        name: "" if idx is None else _strip_tags(cells[idx])
        for name, idx in zip(_ROW_FIELDS, layout)
    }


def _parse_row(body: str) -> dict | None:
    cell_matches = list(CELL_RE.finditer(body))
    field_map = _fields_from_attrs(cell_matches)
    if field_map:
        fields = {k: field_map.get(k, "") for k in _ROW_FIELDS}
    else:
        fields = _fields_from_legacy(cell_matches)
        if fields is None:
            return None
    if fields["outcome"] not in OUTCOMES:
        return None
    return fields


def parse_feedback(path: Path) -> list[dict]:
    entries = []
    if not path.exists():
        return entries
    text = path.read_text(encoding="utf-8-sig")
    for m in ROW_RE.finditer(text):
        row = _parse_row(m.group("body"))
        if row is not None:
            entries.append(row)
    return entries


def parse_runs(path: Path) -> list[dict]:
    runs = []
    if not path.exists():
        return runs
    for f in sorted(path.glob("*.json")):
        if f.name.startswith("."):
            continue  # .run_path_map.json is bookkeeping, not a run
        try:
            # utf-8-sig so a BOM-prefixed run (PS 5.1 pipe) parses instead of
            # raising JSONDecodeError and being silently dropped from priors.
            runs.append(json.loads(f.read_text(encoding="utf-8-sig")))
        except json.JSONDecodeError as e:
            print(f"[feedback] warning: skipping {f.name}: {e}",
                  file=sys.stderr)
            continue
    return runs


def report(entries: list[dict], runs: list[dict] | None = None) -> str:
    out = []
    out.append(f"Total logged uses: {len(entries)}")
    if not entries:
        out.append("No entries yet. Use the skill on a real change — "
                    "log_feedback.py will append to FEEDBACK.html "
                    "automatically.")
        return "\n".join(out)

    outcomes = Counter(e["outcome"] for e in entries)
    out.append("Outcomes:")
    for k in OUTCOMES:
        out.append(f"  {k}: {outcomes.get(k, 0)}")

    confirmed = [e for e in entries if "[confirmed]" in (e.get("note") or "")]
    c_ok = sum(1 for e in confirmed if e["outcome"] == "OK")
    c_bad = sum(1 for e in confirmed if e["outcome"] == "BAD")
    if c_ok + c_bad:
        out.append(
            f"Success rate (confirmed OK/BAD only, n={c_ok + c_bad}): "
            f"{c_ok / (c_ok + c_bad):.0%}"
        )
    unconfirmed = sum(
        1 for e in entries
        if e["outcome"] in ("OK", "BAD") and e not in confirmed
    )
    if unconfirmed:
        out.append(f"Excluded as unconfirmed OK/BAD: {unconfirmed}")

    overrides = [e for e in entries if e["outcome"] == "OVR"]
    if overrides:
        out.append(f"Overrides ({len(overrides)}) — recommendation ignored:")
        for e in overrides[-5:]:
            out.append(f"  {e['date']} | {e['context']} | {e['note']}")

    if runs:
        out.append(f"\nDeliberation runs on disk: {len(runs)}")
        schemes = Counter(_run_scheme(r) for r in runs)
        for s, n in schemes.most_common():
            out.append(f"  scheme={s}: {n}")

    return "\n".join(out)


def _run_scheme(run: dict) -> str:
    """Read the aggregation scheme from a run, tolerating both the legacy
    top-level ``aggregation`` shape and the current ``deliberation_log``
    step shape."""
    agg = run.get("aggregation")
    if isinstance(agg, dict) and agg.get("scheme"):
        return agg["scheme"]
    for step in run.get("deliberation_log") or []:
        if not isinstance(step, dict):
            continue
        if step.get("step") != "aggregate":
            continue
        if step.get("scheme"):
            return step["scheme"]
        result = step.get("result")
        if isinstance(result, dict) and result.get("scheme"):
            return result["scheme"]
    return "?"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--recent", type=int, default=0,
                     help="only consider the N most recent entries")
    ap.add_argument("--runs", action="store_true", help="also scan runs/*.json")
    args = ap.parse_args(argv)

    entries = parse_feedback(FEEDBACK)
    if args.recent:
        entries = entries[-args.recent :]

    runs = parse_runs(RUNS) if args.runs else None
    print(report(entries, runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
