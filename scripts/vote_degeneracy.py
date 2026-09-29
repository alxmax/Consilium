"""Measure Trias vote-pattern degeneracy across runs/*.json.

design audit 2026-05-26 (trias-dialectic-audit-improvements) raised the
hypothesis that Trias's "democratic vote" is theater: 3 personality lenses on
the SAME model are correlated samples, so they would always agree (3-0) and the
vote would carry no information. Reviewer 1/Reviewer 4/Reviewer 5 voted on that
premise.

This script tests the premise empirically instead of assuming it. It scans the
run corpus for Trias runs (those that recorded a `vote_pattern`), tallies the
distribution, and reports the 3-0 unanimity rate. The decision rule:

- 3-0 rate > --degenerate-threshold (default 0.85) with n >= --min-n
  → `vote_degenerate: true` — the lenses do not decorrelate; the vote adds no
    signal over a single Sequential run, and the 3-0=0.95 confidence is suspect.
- 3-0 rate <= threshold → the vote is MEANINGFUL: personalities disagree often
  enough that the majority vote can change the outcome vs a single run.
- n < --min-n → `insufficient`: not enough Trias runs to conclude
  (Reviewer 8 gate).

Unanimity is 3-0 ONLY. A 2-0 pattern is a *veto* (one personality had all
candidates vetoed), not three lenses agreeing — it is tallied separately as
`veto_rate` rather than folded into unanimity. Runs are admitted only when the
serialized report declares `"mode": "trias"` / `"trias_split"` exactly, so a
non-Trias run that merely cites a vote_pattern in its body is not counted.

Read-only. Does not touch any voice prompt, mode file, or the live pipeline.

CLI:
    python scripts/vote_degeneracy.py
    python scripts/vote_degeneracy.py --runs-dir .consilium/runs --min-n 20
    python scripts/vote_degeneracy.py --json
"""
# implements: CONSILIUM-VOTE-DEGENERACY-001

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS = ROOT / ".consilium" / "runs"

# A vote_pattern is "N-N" (2-personality / legacy) or "N-N-N" (3-personality).
_VOTE_PATTERN_RE = re.compile(r'"vote_pattern"\s*:\s*"(\d-\d(?:-\d)?)"')

# A run is corpus-admissible only if it is a *genuine* Trias run. We match the
# mode marker with the closing quote anchored, so `trias` / `trias_split` count
# but composite modes like `trias_plus_dialectic_skeptic_defenders` or
# `meta_orchestrator_2_subagents` do NOT — those runs merely *cite* a
# vote_pattern in their body and would otherwise contaminate the count.
_TRIAS_MODE_RE = re.compile(r'"mode"\s*:\s*"(?:trias|trias_split)"')

DEGENERATE_THRESHOLD = 0.85
MIN_N = 20


def is_trias_run(text: str) -> bool:
    """True if the serialized run declares mode trias / trias_split exactly.

    Text-based (not json.loads) so a malformed-but-genuine Trias report is still
    counted, and so a non-Trias run that quotes a vote_pattern is excluded.
    """
    return bool(_TRIAS_MODE_RE.search(text))


def extract_vote_pattern(text: str) -> str | None:
    """Return the run's canonical vote_pattern, or None if absent.

    A Trias report records the pattern at run level AND may echo other runs'
    patterns inside nested deliberation context (e.g. a meta-audit that cites
    `trias_input.vote_pattern`). The first match is the run-level value emitted
    by build_report — nested citations appear later in the serialized JSON.
    """
    m = _VOTE_PATTERN_RE.search(text)
    return m.group(1) if m else None


def scan(runs_dir: Path) -> tuple[Counter, list[dict]]:
    patterns: Counter[str] = Counter()
    runs: list[dict] = []
    for f in sorted(runs_dir.glob("*.json")):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if not is_trias_run(text):
            continue
        vp = extract_vote_pattern(text)
        if vp:
            patterns[vp] += 1
            runs.append({"run": f.name, "vote_pattern": vp})
    return patterns, runs


def assess(patterns: Counter, threshold: float, min_n: int) -> dict:
    n = sum(patterns.values())
    # Unanimity is 3-0 ONLY. 2-0 is a veto (one personality had all candidates
    # vetoed), not three lenses agreeing — folding it into unanimity overstates
    # decorrelation. It is reported separately as veto_rate so the signal is not
    # lost. (review 2026-05-27 — Reviewer 1/Reviewer 8/Reviewer 6.)
    unanimous = patterns.get("3-0", 0)
    veto = patterns.get("2-0", 0)
    rate = (unanimous / n) if n else None
    veto_rate = (veto / n) if n else None
    if n < min_n:
        verdict = "insufficient"
        note = (
            f"n={n} < min_n={min_n}; not enough Trias runs to "
            f"conclude (Reviewer 8 gate)."
        )
    elif rate is not None and rate > threshold:
        verdict = "vote_degenerate"
        note = (
            f"3-0 unanimity rate {rate:.0%} > {threshold:.0%}: "
            f"lenses do not decorrelate; the majority vote adds no "
            f"signal over a single Sequential run."
        )
    else:
        verdict = "vote_meaningful"
        note = (
            f"3-0 unanimity rate {rate:.0%} <= {threshold:.0%}: "
            f"personalities disagree often enough that the vote can "
            f"change the outcome - the vote carries information."
        )
    return {
        "n": n,
        "distribution": dict(patterns.most_common()),
        "unanimity_rate": round(rate, 4) if rate is not None else None,
        "veto_rate": round(veto_rate, 4) if veto_rate is not None else None,
        "veto_count": veto,
        "degenerate_threshold": threshold,
        "min_n": min_n,
        "verdict": verdict,
        "note": note,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--runs-dir", default=str(DEFAULT_RUNS),
        help="runs directory (default: .consilium/runs)",
    )
    ap.add_argument(
        "--degenerate-threshold", type=float,
        default=DEGENERATE_THRESHOLD,
        help=(
            "unanimity rate above which the vote is judged "
            "degenerate (default 0.85)"
        ),
    )
    ap.add_argument(
        "--min-n", type=int, default=MIN_N,
        help="minimum Trias runs to render a verdict (default 20)",
    )
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    args = ap.parse_args(argv)

    runs_dir = Path(args.runs_dir)
    if not runs_dir.is_dir():
        print(f"runs dir not found: {runs_dir}", file=sys.stderr)
        return 2

    patterns, _ = scan(runs_dir)
    report = assess(patterns, args.degenerate_threshold, args.min_n)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    print(f"Trias vote-pattern degeneracy  (runs: {runs_dir})")
    print(f"  n = {report['n']} runs with a vote_pattern")
    for pat, count in report["distribution"].items():
        share = count / report["n"] if report["n"] else 0
        print(f"    {pat}: {count}  ({share:.0%})")
    if report["unanimity_rate"] is not None:
        print(f"  3-0 unanimity rate: {report['unanimity_rate']:.0%}")
    if report["veto_rate"] is not None:
        print(
            f"  2-0 veto rate:      {report['veto_rate']:.0%}  "
            f"({report['veto_count']} run(s))"
        )
    print(f"  verdict: {report['verdict']}")
    print(f"  {report['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
