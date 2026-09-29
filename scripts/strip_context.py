"""Strip cross-voice context to reduce contamination in sequential mode.

In sequential mode, the same agent plays all three voices in one
context window. Generator's rationales leak into Control's verdict
write-up; Control's issue language leaks into Conservator's framing.
This script projects the previous voice's output down to the minimum
fields the next voice actually needs to do its job.

Two JSON projections:

- ``--for control`` reads a Generator output and emits the candidate
  list with ONLY ``id``, ``summary``, ``sketch``. Drops ``rationale``
  (rhetoric that biases technical validation).

- ``--for conservator`` reads a Control output and emits valid
  verdicts with ONLY ``id`` plus the matching candidate's ``id``,
  ``summary``, ``sketch``. Drops ``issues`` and ``notes`` (rhetoric
  that biases risk scoring), and skips ``valid: false`` entries
  entirely — Conservator should never score those.

Input shape for ``--for conservator`` is the union of Generator and
Control outputs, passed as one JSON object::

    {
      "candidates": [...],   # from Generator
      "verdicts":   [...]    # from Control
    }

This is intentional: Conservator needs the original ``sketch`` text
(which Control doesn't carry forward) to score diff_size and scope_drift,
but should not see Control's issue descriptions.

One text truncation mode (Phase 1 — Trias context budget):

- ``--truncate-text MAX_TOKENS`` reads raw text from stdin and emits
  the first MAX_TOKENS*4 characters with a truncation marker appended
  when the text exceeds the budget. Approximation: 1 token ≈ 4 chars.
  Used by Trias orchestration to cap the conversation context sent to
  each personality sub-agent (default 15 000 tokens ≈ 60 000 chars).

CLI:
    cat generator_out.json | python scripts/strip_context.py --for control
    cat combined.json      | python scripts/strip_context.py --for conservator
    cat context.txt        | python scripts/strip_context.py
        --truncate-text 15000
"""
# implements: CONSILIUM-STRIP-CONTEXT-001

from __future__ import annotations

import argparse
import json
import sys

from utils import force_utf8_streams


CANDIDATE_KEEP = ("id", "summary", "sketch")


def strip_for_control(data: dict) -> dict:
    candidates = data.get("candidates") or []
    return {
        "candidates": [
            {k: c[k] for k in CANDIDATE_KEEP if k in c}
            for c in candidates
            if isinstance(c, dict)
        ]
    }


def strip_for_conservator(data: dict) -> dict:
    candidates = {}
    for c in (data.get("candidates") or []):
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if not cid:
            continue
        candidates[cid] = c
    verdicts = data.get("verdicts") or []
    out = []
    for v in verdicts:
        if not isinstance(v, dict) or not v.get("valid"):
            continue
        cid = v.get("id")
        if not cid or cid not in candidates:
            continue
        c = candidates[cid]
        out.append({k: c[k] for k in CANDIDATE_KEEP if k in c})
    return {"candidates": out}


PROJECTIONS = {
    "control": strip_for_control,
    "conservator": strip_for_conservator,
}

_TRUNCATION_MARKER = (
    "\n\n[... context truncated to ~{tokens} tokens for Trias sub-agent ...]"
)


def strip_for_trias(text: str, max_tokens: int = 15_000) -> str:
    """Truncate raw context text to approximately max_tokens
    (≈ 4 chars/token).

    Returns text unchanged when it fits within the budget.  When truncation
    is needed, appends a marker so the sub-agent knows the context was cut.
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + _TRUNCATION_MARKER.format(tokens=max_tokens)


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    ap = argparse.ArgumentParser(description=__doc__)
    mode_group = ap.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--for",
        dest="voice",
        choices=sorted(PROJECTIONS),
        help=(
            "which downstream voice should receive the stripped output "
            "(JSON mode)"
        ),
    )
    mode_group.add_argument(
        "--truncate-text",
        dest="truncate_tokens",
        type=int,
        metavar="MAX_TOKENS",
        help=(
            "truncate stdin plain text to approximately MAX_TOKENS "
            "(text mode, not JSON)"
        ),
    )
    ap.add_argument(
        "--input",
        type=argparse.FileType("r", encoding="utf-8-sig"),
        default=sys.stdin,
        help="input file (default: stdin)",
    )
    args = ap.parse_args(argv)

    if args.truncate_tokens is not None:
        text = args.input.read()
        sys.stdout.write(strip_for_trias(text, args.truncate_tokens))
        return 0

    # Clean exit on malformed/BOM-prefixed input (PS 5.1 pipes prepend a BOM
    # on stdin) — one stderr line + exit 2, matching
    # build_report/validate_report.
    try:
        data = json.loads(args.input.read().lstrip("﻿"))
    except json.JSONDecodeError as exc:
        print(f"strip_context: invalid JSON input: {exc}", file=sys.stderr)
        return 2
    result = PROJECTIONS[args.voice](data)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
