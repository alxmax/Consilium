"""Uniform read API for Consilium's three memory tiers.

Memory is already split across three layers; this script gives them
a single CLI/import surface so a future agent can ask "what does
Consilium remember about X" without learning where each tier lives.

Tiers:

- **short** — current deliberation context. Lives in the agent's
  conversation window only. This script returns a stub describing
  what *would* be there (the bundle being deliberated on); the actual
  short-term content is only accessible to the agent itself.

- **medium** — ``runs/*.json``, one file per deliberation. Episodic.
  Read by ``priors.py`` at Step 0. Without a query, returns the most
  recent N as summaries.
  With ``--query``, filters by substring against ``success_criterion``
  and ``chosen_approach``.

- **long** — ``FEEDBACK.html`` plus the derived signals from
  ``priors.py``. Aggregate. Survives across deliberations. With
  ``--query``, filters by substring against ``context`` and
  ``chosen``. Confirmed-outcome rows (those with ``[confirmed]`` in
  note) are flagged in the output so callers can weight them higher.

CLI:
    python scripts/memory.py --tier short
    python scripts/memory.py --tier medium --n 5
    python scripts/memory.py --tier medium --query auth
    python scripts/memory.py --tier long --query rollback
    python scripts/memory.py --tier all --query feedback  # union across tiers
    python scripts/memory.py --tier long --feedback-file path/to/FEEDBACK.html
    python scripts/memory.py --tier medium --runs-dir path/to/runs/
"""
# implements: CONSILIUM-MEMORY-001

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from utils import FEEDBACK_PATH, RUNS_DIR, force_utf8_streams

ROOT = Path(__file__).resolve().parent.parent
RUNS = RUNS_DIR
FEEDBACK = FEEDBACK_PATH


_FB_PATH = ROOT / "scripts" / "feedback.py"
_spec = importlib.util.spec_from_file_location("consilium_feedback", _FB_PATH)
assert _spec and _spec.loader
_feedback = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_feedback)
parse_feedback = _feedback.parse_feedback


CONFIRMED_MARKER = "[confirmed]"


def read_short() -> dict:
    """Short-term memory is the active deliberation; agent-only access."""
    return {
        "tier": "short",
        "note": (
            "session-local; not persisted. The deliberation bundle being "
            "assembled at Steps 1-5b lives here. Outside the agent's "
            "context window this tier is empty."
        ),
        "entries": [],
    }


def _run_summary(run: dict, path: Path) -> dict:
    return {
        "run": path.name,
        "date": path.name[:10],
        "success_criterion": run.get("success_criterion", ""),
        "chosen": run.get("chosen_approach"),
        "confidence": run.get("confidence"),
    }


def _matches(text: str, q: str) -> bool:
    return q.lower() in text.lower()


def read_medium(
    n: int = 10, query: str | None = None, runs: Path = RUNS
) -> dict:
    if not runs.exists():
        return {"tier": "medium", "entries": [], "total": 0}
    files = sorted(runs.glob("*.json"), reverse=True)
    entries: list[dict] = []
    for f in files:
        try:
            # utf-8-sig so a BOM-prefixed run (PS 5.1 pipe) parses instead of
            # raising JSONDecodeError and being silently dropped — matches the
            # convention in feedback.py/priors.py/render_feedback_html.py.
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            continue
        summary = _run_summary(data, f)
        if query:
            hay = f"{summary['success_criterion']} {summary['chosen'] or ''}"
            if not _matches(hay, query):
                continue
        entries.append(summary)
        if len(entries) >= n:
            break
    return {"tier": "medium", "entries": entries, "total": len(files)}


def read_long(
    query: str | None = None, n: int = 20, feedback: Path = FEEDBACK
) -> dict:
    rows = parse_feedback(feedback)
    total = len(rows)
    if query:
        rows = [
            r for r in rows
            if _matches(
                f"{r['context']} {r['chosen']} {r.get('note', '')}",
                query,
            )
        ]
        rows = rows[-n:]
    else:
        rows = rows[-n:]
    out = []
    for r in rows:
        out.append({
            "date": r["date"],
            "context": r["context"],
            "chosen": r["chosen"],
            "outcome": r["outcome"],
            "confirmed": CONFIRMED_MARKER in (r.get("note") or ""),
            "note": r.get("note", ""),
        })
    return {"tier": "long", "entries": out, "total": total}


def read_all(
    query: str | None, n: int, feedback: Path = FEEDBACK, runs: Path = RUNS
) -> dict:
    return {
        "short": read_short(),
        "medium": read_medium(n=n, query=query, runs=runs),
        "long": read_long(query=query, n=n, feedback=feedback),
    }


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tier", choices=("short", "medium", "long", "all"), default="all"
    )
    ap.add_argument(
        "--n", type=int, default=10, help="cap on entries returned per tier"
    )
    ap.add_argument(
        "--query", default=None, help="substring filter (medium/long only)"
    )
    ap.add_argument(
        "--feedback-file", metavar="PATH",
        help=(
            "override FEEDBACK.html path "
            "(default: .consilium/FEEDBACK.html)"
        ),
    )
    ap.add_argument(
        "--runs-dir", metavar="PATH",
        help="override runs/ directory path (default: .consilium/runs)",
    )
    args = ap.parse_args(argv)

    feedback = (
        Path(args.feedback_file).resolve() if args.feedback_file else FEEDBACK
    )
    runs = Path(args.runs_dir).resolve() if args.runs_dir else RUNS

    if args.tier == "short":
        result = read_short()
    elif args.tier == "medium":
        result = read_medium(n=args.n, query=args.query, runs=runs)
    elif args.tier == "long":
        result = read_long(query=args.query, n=args.n, feedback=feedback)
    else:
        result = read_all(
            query=args.query, n=args.n, feedback=feedback, runs=runs
        )

    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
