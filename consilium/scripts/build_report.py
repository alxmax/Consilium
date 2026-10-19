"""Assemble the canonical deliberation report from intermediate voice outputs.

Reads a bundle (JSON) on stdin combining Generator/Control/Conservator
outputs plus aggregator + confidence results, and emits the report shape
that ``runs/README.md`` documents and ``validate_report.py`` enforces.

Eliminates the manual JSON assembly that used to live in the agent's head
between Step 5b and Step 6 — a step that was easy to get wrong (typo a
field, forget alternatives, mis-nest deliberation_log).

Input bundle shape on stdin:

    {
      "success_criterion": "REQUIRED",
      "verification":      "REQUIRED",
      "generator":   {"candidates": [...]},                  // from Step 2
      "control":     {"verdicts":   [...]},                  // from Step 3
      "conservator": {"scores":     [...]},                  // from Step 4
      "aggregate":   {"scheme":"...", "chosen":"...", ...},
      // from Step 5 (aggregator.py)
      "confidence":  {"confidence":0.85, ...},
      // from Step 5b (confidence.py)
      "telemetry":   {...},                                  // optional, Step 6
      "alternatives_limit": 3
      // optional, default 3
    }

Output: the canonical full report (or skipped report if ``skipped: true``
is set on the bundle root, in which case the bundle only needs
``success_criterion`` + ``verification`` + ``skip_reason`` + ``signals``).

Voice scores in the report are derived from the chosen candidate's
own scores in the conservator/control/generator inputs (or defaults).
The ``alternatives`` list is the runner-up candidates (capped at
``alternatives_limit``) with ``why_not`` derived from Control issues
or Conservator factors when present.

Exits 1 on missing required field. Exits 2 on malformed JSON.
Run ``validate_report.py`` after to confirm Principle #4 compliance.

CLI:
    cat bundle.json | python scripts/build_report.py | python
    scripts/validate_report.py
    python scripts/build_report.py --input bundle.json
"""
# implements: CONSILIUM-BUILD-REPORT-001

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from utils import force_utf8_streams, issue_penalty, validate_keys
from version import consilium_ref, consilium_version


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _telemetry_gaps(telemetry: object) -> list[str]:
    """What a cost analysis would be missing from this telemetry block:
    ``dispatch_count`` (an int) and at least one measured (> 0) latency, at
    the top level or on a voice. Latency 0 is the "not measured" placeholder."""
    tele = telemetry if isinstance(telemetry, dict) else {}
    gaps: list[str] = []
    dc = tele.get("dispatch_count")
    if not (isinstance(dc, int) and not isinstance(dc, bool)):
        gaps.append("dispatch_count")
    voices = tele.get("voices")
    latencies = [tele.get("latency_ms")] + [
        v.get("latency_ms")
        for v in (voices.values() if isinstance(voices, dict) else [])
        if isinstance(v, dict)
    ]
    if not any(
        isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0
        for x in latencies
    ):
        gaps.append("latency_ms")
    return gaps


def _stamp_provenance(report: dict) -> dict:
    """Stamp repo version provenance into every report's telemetry block.

    consilium_version = human display stamp; consilium_ref = the resolvable
    diff operand drift checks read (empty on a dirty/unknown tree).
    build_report is one of three report producers — the two hand-built
    SKILL.md templates (scale_down, prior-deliberation passthrough) stamp
    the same two fields inline.
    """
    tele = report.get("telemetry")
    if not isinstance(tele, dict):
        tele = {}
        report["telemetry"] = tele
    tele["consilium_version"] = consilium_version()
    tele["consilium_ref"] = consilium_ref()
    return report


def _candidate_by_id(items: list[dict], cid: str) -> dict | None:
    for item in items:
        if isinstance(item, dict) and item.get("id") == cid:
            return item
    return None


def _conservator_risk(score: dict) -> float | None:
    # Conservator schema (prompts/voices/conservator.md): risk lives at
    # regression_risk.net_concern. Legacy bundles may have top-level risk_score.
    rr = score.get("regression_risk")
    if isinstance(rr, dict) and isinstance(rr.get("net_concern"), (int, float)):
        return float(rr["net_concern"])
    legacy = score.get("risk_score")
    if isinstance(legacy, (int, float)):
        return float(legacy)
    return None


def _voice_scores_for(
    chosen: str | None, control: dict, conservator: dict
) -> dict | None:
    if chosen is None:
        return None
    verdict = _candidate_by_id(control.get("verdicts") or [], chosen) or {}
    if not verdict:
        print(
            f"build_report: no control verdict found for chosen={chosen!r}",
            file=sys.stderr,
        )
    score = _candidate_by_id(conservator.get("scores") or [], chosen) or {}
    # An empty verdict ({}) naturally yields control_score 0.0 here (no
    # `valid` key), so no separate not-found branch is needed.
    issues = verdict.get("issues") or []
    control_score = (
        0.0
        if not verdict.get("valid")
        else max(0.3, 1.0 - sum(issue_penalty(i) for i in issues))
    )
    risk = _conservator_risk(score)
    return {
        "generator": (
            0.5
            if chosen == "do_nothing" or chosen.startswith("adversarial_")
            else 1.0
        ),
        "control": round(control_score, 3),
        "conservator": 0.5 if risk is None else risk,
    }


def _why_not(
    verdict: dict | None, score: dict | None, no_chosen: bool = False
) -> str:
    bits: list[str] = []
    if verdict and not verdict.get("valid"):
        details = ", ".join(
            i.get("category", "?")
            for i in (verdict.get("issues") or [])
            if isinstance(i, dict)
        )
        bits.append(
            f"control: invalid ({details})" if details else "control: invalid"
        )
    elif verdict and verdict.get("issues"):
        first = verdict["issues"][0] if verdict["issues"] else {}
        if isinstance(first, dict):
            detail = first.get("detail")
            if isinstance(detail, str):
                bits.append(f"control: {detail[:80]}")
    risk = _conservator_risk(score) if score else None
    if risk is not None and risk >= 0.5:
        bits.append(f"risk={risk:.2f}")
    fallback = "all candidates vetoed" if no_chosen else "ranked below chosen"
    return "; ".join(bits) or fallback


def validate_input(bundle: dict) -> None:
    """Validate build_report bundle has required top-level fields.

    For skipped bundles, only success_criterion and verification are required.
    For normal bundles, generator/control/conservator are also required.
    """
    if bundle.get("skipped") is True:
        validate_keys(
            bundle,
            ["success_criterion", "verification"],
            context="build_report bundle",
        )
    else:
        validate_keys(
            bundle,
            [
                "success_criterion",
                "verification",
                "generator",
                "control",
                "conservator",
            ],
            context="build_report bundle",
        )


def _alternatives(
    generator: dict,
    control: dict,
    conservator: dict,
    aggregate: dict,
    limit: int,
) -> list[dict]:
    if limit <= 0:
        return []
    chosen = aggregate.get("chosen")
    no_chosen = chosen is None
    candidates = generator.get("candidates") or []
    verdicts = control.get("verdicts") or []
    scores = conservator.get("scores") or []
    out: list[dict] = []
    for cand in candidates:
        cid = cand.get("id")
        if not cid or cid == chosen:
            continue
        if len(out) >= limit:
            break
        out.append({
            "id": cid,
            "summary": cand.get("summary", ""),
            "why_not": _why_not(
                _candidate_by_id(verdicts, cid),
                _candidate_by_id(scores, cid),
                no_chosen=no_chosen,
            ),
        })
    return out


def _build_skipped(bundle: dict) -> dict:
    for required in ("success_criterion", "verification", "skip_reason"):
        v = bundle.get(required)
        if not isinstance(v, str) or not v.strip():
            raise ValueError(
                f"skipped bundle missing required field: {required}"
            )
    return {
        "success_criterion": bundle["success_criterion"],
        "verification": bundle["verification"],
        "chosen_approach": "skipped",
        "skipped": True,
        "skip_reason": bundle["skip_reason"],
        "signals": bundle.get("signals", {}),
        "voice_scores": None,
        "confidence": None,
        "alternatives": [],
        "deliberation_log": [],
    }


def build(bundle: dict) -> dict:
    if bundle.get("skipped") is True:
        return _stamp_provenance(_build_skipped(bundle))

    for required in ("success_criterion", "verification"):
        v = bundle.get(required)
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"bundle missing required field: {required}")

    generator = bundle.get("generator") or {}
    control = bundle.get("control") or {}
    conservator = bundle.get("conservator") or {}
    aggregate = bundle.get("aggregate") or {}
    confidence_block = bundle.get("confidence") or {}

    if "chosen" not in aggregate:
        raise ValueError("bundle.aggregate missing 'chosen' field")
    chosen = aggregate["chosen"]
    if chosen is not None and not isinstance(chosen, str):
        raise ValueError("bundle.aggregate.chosen must be string or null")

    # Resolve the default explicitly: `or 3` would treat the integer 0 as falsy,
    # so `alternatives_limit: 0` ("suppress all alternatives") silently became 3
    # while -1 worked — defeating the `if limit <= 0: return []` guard in
    # _alternatives. Honor 0.
    _raw_limit = bundle.get("alternatives_limit")
    alt_limit = int(_raw_limit) if isinstance(_raw_limit, (int, float)) else 3

    report: dict[str, Any] = {
        "success_criterion": bundle["success_criterion"],
        "verification": bundle["verification"],
        "chosen_approach": chosen,
        "reasoning": bundle.get("reasoning")
        or _default_reasoning(aggregate, confidence_block),
        "alternatives": _alternatives(
            generator, control, conservator, aggregate, alt_limit
        ),
        "voice_scores": _voice_scores_for(chosen, control, conservator),
        "confidence": confidence_block.get("confidence"),
        # pipeline_executed: True when the 3-voice deliberation pipeline ran
        # end-to-end. Hand-built reports (trivial-direct from scale_down,
        # prior-deliberation passthrough) set this to False in their
        # template — see SKILL.md Step 2.
        "pipeline_executed": True,
        "deliberation_log": _deliberation_log(
            generator, control, conservator, aggregate
        ),
    }
    _attach_optional_fields(report, bundle, control, aggregate)
    gaps = _telemetry_gaps(report.get("telemetry"))
    if gaps:
        # Marked, not rejected: older runs and hand-built bundles stay
        # readable, but a cost rollup can see which reports to distrust.
        report["telemetry_incomplete"] = True
        report["telemetry_gaps"] = gaps
    return _stamp_provenance(report)


def _deliberation_log(
    generator: dict,
    control: dict,
    conservator: dict,
    aggregate: dict,
) -> list[dict]:
    return [
        {
            "step": "generator",
            "candidates": generator.get("candidates") or [],
        },
        {
            "step": "control",
            "verdicts": control.get("verdicts") or [],
        },
        {
            "step": "conservator",
            "scores": conservator.get("scores") or [],
        },
        {
            "step": "aggregate",
            "scheme": aggregate.get("scheme", "?"),
            "result": aggregate,
        },
    ]


def _attach_optional_fields(
    report: dict, bundle: dict, control: dict, aggregate: dict
) -> None:
    """Pass through the optional bundle fields onto the report."""
    # Persist Control's declared falsifier so mark_outcome.py --auto-suggest can
    # read it back when the outcome is scored later (consumer wired 2026-07-07;
    # design review 2026-07-07_011914 required consumer-first).
    _control_step = report["deliberation_log"][1]
    if "strongest_objection" in control:
        _control_step["strongest_objection"] = control["strongest_objection"]
    if "no_blocking_defect_attested" in control:
        _control_step["no_blocking_defect_attested"] = control[
            "no_blocking_defect_attested"
        ]
    if "telemetry" in bundle:
        report["telemetry"] = bundle["telemetry"]
    if "deliberation_quality" in bundle:
        # Legacy advisory block (its producer, the meta-critic step, is
        # deleted); still passed through so older bundles round-trip.
        report["deliberation_quality"] = bundle["deliberation_quality"]
    # Trias mode: pass through team/personalities/vote_pattern/dissent/abstained
    # fields when present in the bundle. These come from the orchestrator after
    # the team_vote aggregator scheme runs.
    if "team" in bundle:
        report["team"] = bundle["team"]
    if "personalities" in bundle:
        report["personalities"] = bundle["personalities"]
    if "vote_pattern" in bundle:
        report["vote_pattern"] = bundle["vote_pattern"]
    # B3: per-personality choices breakdown (orchestrator populates this
    # after step 3)
    if "personality_choices" in bundle:
        report["personality_choices"] = bundle["personality_choices"]
    if "vote_skipped" in bundle:
        report["vote_skipped"] = bundle["vote_skipped"]
    if isinstance(aggregate, dict):
        if "dissent" in aggregate:
            report["dissent"] = aggregate["dissent"]
        if "abstained" in aggregate:
            report["abstained"] = aggregate["abstained"]


def _default_reasoning(aggregate: dict, confidence_block: dict) -> str:
    chosen = aggregate.get("chosen")
    scheme = aggregate.get("scheme", "?")
    if chosen is None:
        if scheme == "team_vote":
            vote_pattern = aggregate.get("vote_pattern", "unknown")
            return (
                f"deliberation fragmented (vote_pattern={vote_pattern}); "
                "orchestrator must intervene"
            )
        return f"all candidates vetoed under {scheme}; see retry_suggested"
    conf = confidence_block.get("confidence")
    conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "?"
    return f"{scheme} picked {chosen} (confidence={conf_s})"


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input",
        type=argparse.FileType("r", encoding="utf-8"),
        default=sys.stdin,
        help="JSON bundle file (default: stdin)",
    )
    args = ap.parse_args(argv)

    try:
        bundle = json.load(args.input)
    except json.JSONDecodeError as exc:
        _err(f"invalid JSON: {exc}")
        return 2
    if not isinstance(bundle, dict):
        _err("bundle must be a JSON object")
        return 2

    try:
        validate_input(bundle)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    try:
        report = build(bundle)
    except ValueError as exc:
        _err(str(exc))
        return 1

    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
