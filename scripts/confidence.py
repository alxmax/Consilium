"""Derive report confidence from voice-score variance.

Replaces the magic number that used to live in the final report's
``confidence`` field. The intuition: when the three voices agree on a
candidate, confidence is high; when they disagree, confidence is low.

Two signals get folded in:

1. **Inter-voice agreement on the chosen candidate.** Generator and
   Control emit utility (1 = good), but Conservator emits risk
   (1 = bad), so we flip Conservator into safety = 1 - risk before
   measuring spread. Agreement is then
   ``1 - stdev([gen, ctrl, safety]) / max_stdev``, where
   ``max_stdev`` is the maximum possible stdev for 3 values in [0,1]
   (~0.471 for the bimodal case [0,0,1]). Without the flip, the
   metric would punish exactly the cases we want — Gen high, Ctrl
   high, Conservator low (= "everyone thinks this is a great, safe
   candidate") would register as high disagreement.
2. **Separation from runner-up.** ``utility(chosen) - max_utility(others)``,
   where ``utility(c) = mean(gen, ctrl, 1 - cons)``. If there is no
   runner-up, this term is 1.0.

Final confidence is a weighted blend: 0.7 * agreement + 0.3 * separation.
Clamped to [0.05, 0.99] — we never claim absolute certainty, nor zero.

CALIBRATION NOTE (R2 audit 2026-05-17): ``agreement`` measures role-prompt
divergence within one run — how much Generator/Control/Conservator disagree
with each other. It is NOT inter-run stability. Running the same input twice
may produce different voice scores (predicted pstdev 0.12–0.18 for
risk_score). Conservator scores are anchored via categorical formula;
Generator/Control scores are self-assigned unanchored floats.

Input format on stdin (JSON):
    {
      "candidates": [
        {
          "id": "chosen_one",
          "scores": {"generator": 0.8, "control": 0.9, "conservator": 0.3}
        },
        {
          "id": "runner_up",
          "scores": {"generator": 0.6, "control": 0.7, "conservator": 0.4}
        }
      ],
      "chosen": "chosen_one"
    }

Output: {"confidence": 0.84, "agreement": 0.91, "separation": 0.20}

If ``chosen`` is null or missing from candidates, returns
``{"confidence": null, "reason": "..."}`` — confidence is undefined
without a winner. Callers should fall back to their own heuristic.

CLI:
    cat aggregation.json | python scripts/confidence.py
"""
# implements: CONSILIUM-CONFIDENCE-001

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

from utils import force_utf8_streams, validate_keys

VOICES = ("generator", "control", "conservator")
# pstdev of [0, 0, 1] = sqrt(2/9) ≈ 0.4714
MAX_STDEV_3VALS = (2 / 9) ** 0.5
AGREEMENT_WEIGHT = 0.7
SEPARATION_WEIGHT = 0.3
CONFIDENCE_FLOOR = 0.05
CONFIDENCE_CEIL = 0.99

_MODES_DIR = pathlib.Path(__file__).parent.parent / "modes"

# Hardcoded fallback used when modes/*.md files are absent (e.g. older
# installs).
_FLOOR_FALLBACK: dict[str, float] = {
    "sequential": 0.70,
    "sequential_scale_down": 0.70,
    "dialectic": 0.75,
    "trias": 0.80,
}


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse flat YAML frontmatter between --- delimiters. Stdlib-only."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next(
        (i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None
    )
    if end is None:
        return {}
    result: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def _load_mode_floors() -> dict[str, float]:
    """Read confidence_floor from modes/*.md frontmatter. Falls back to
    hardcoded dict."""
    if not _MODES_DIR.is_dir():
        return dict(_FLOOR_FALLBACK)
    floors: dict[str, float] = {}
    for f in sorted(_MODES_DIR.glob("*.md")):
        try:
            fm = _parse_frontmatter(f.read_text(encoding="utf-8"))
        except OSError:
            continue
        name = fm.get("name", "").strip()
        raw = fm.get("confidence_floor", "").strip()
        if name and raw and raw != "N/A":
            try:
                floors[name] = float(raw)
            except ValueError:
                pass
    if not floors:
        return dict(_FLOOR_FALLBACK)
    # sequential_scale_down inherits sequential floor when not explicitly
    # defined
    if "sequential" in floors and "sequential_scale_down" not in floors:
        floors["sequential_scale_down"] = floors["sequential"]
    return floors


# E1: mode-specific confidence floors. Loaded from modes/*.md frontmatter;
# falls back to hardcoded dict when modes/ is absent (e.g. older installs).
MODE_CONFIDENCE_FLOOR: dict[str, float] = _load_mode_floors()


# UNCALIBRATED PRIORS — these numbers encode inter-personality CONSENSUS, not
# validated accuracy. vote_degeneracy.py (n=25) confirms the ORDERING is earned
# (3-0 occurs only ~48% of the time, so unanimity is a real signal, not forced),
# but the specific MAGNITUDES are not calibrated against correctness: on the
# transport_choice benchmark task a 3-0 was recorded on a WRONG answer (32/100).
# Agreement != truth. Until a corpus of >=20 labeled (vote_pattern, outcome)
# pairs yields a calibration curve (Brier/AUC), treat these as ordered priors,
# not probabilities. (review 2026-05-26 round 2, D1 — 5 MODIFY / 2 STOP / 2
# GO.)
VOTE_PATTERN_CONFIDENCE = {
    "3-0": 0.95,
    # dissent: one personality chose a different candidate (recoverable)
    "2-1": 0.75,
    # veto: one personality had all candidates vetoed (stronger risk signal)
    "2-0": 0.70,
    "1-1-1": None,
    "1-1-0": None,
    "1-0-0": None,
    "0-0-0": None,
}

# Decisive Trias patterns (a winner emerged) — derived from the canonical
# map so it cannot drift. Used by check_mode_floor to exempt
# structurally-bounded splits (2-1/2-0) from the WEAK floor flag. Null
# patterns carry confidence=None and are already handled by the
# confidence-is-None branch.
_DECISIVE_VOTE_PATTERNS = frozenset(
    p for p, c in VOTE_PATTERN_CONFIDENCE.items() if c is not None
)


def check_mode_floor(
    mode: str, confidence: float | None, vote_pattern: str | None = None
) -> dict:
    """Return {below_floor: bool, floor: float|None, outcome_hint: str}.

    Callers check this after confidence derivation and log WEAK in FEEDBACK.html
    when below_floor is True. outcome_hint is 'WEAK' or 'OK' (advisory only).

    Trias confidence is derived from the democratic vote pattern, not
    voice-score variance: a decisive split (2-1=0.75, 2-0=0.70) sits
    *structurally* below the 0.80 Trias floor without signalling a weak
    deliberation. When ``vote_pattern`` is one of the decisive patterns
    (3-0/2-1/2-0) the run is exempt from the WEAK flag, so the floor
    catches only genuinely weak runs (score-based modes that
    underperform, or null/deadlock patterns whose confidence is already None).
    The exempt set is derived from VOTE_PATTERN_CONFIDENCE (single source — no
    drift), so it cannot diverge from the canonical patterns.
    """
    floor = MODE_CONFIDENCE_FLOOR.get(mode)
    if floor is None or confidence is None:
        return {"below_floor": False, "floor": floor, "outcome_hint": "OK"}
    if vote_pattern in _DECISIVE_VOTE_PATTERNS:
        return {
            "below_floor": False,
            "floor": floor,
            "outcome_hint": "OK",
            "exempt": "decisive_vote_pattern",
        }
    below = confidence < floor
    return {
        "below_floor": below,
        "floor": floor,
        "outcome_hint": "WEAK" if below else "OK",
    }

# Sentinel is the conservative-leaning personality (weights K=0.40). When it
# dissents or abstains, that carries more risk-signal than the same outcome
# from Essentialist or Verifier — drop confidence below the PEND threshold so
# the orchestrator prompts the user instead of auto-shipping.
SENTINEL_DISSENT_PENALTY = 0.10
SENTINEL_ABSTAIN_PENALTY = 0.15
SENTINEL_NAME = "sentinel"


def _sentinel_involved(items: list[dict] | None, key: str) -> bool:
    if not items:
        return False
    return any(
        isinstance(it, dict) and it.get(key) == SENTINEL_NAME for it in items
    )


def confidence_from_vote_pattern(
    pattern: str,
    dissent: list[dict] | None = None,
    abstained: list[dict] | None = None,
) -> dict:
    """Trias mode — derive confidence directly from democratic vote pattern.

    Returns the canonical confidence shape (confidence, agreement, separation)
    so downstream code doesn't need to branch on whether the input was Trias
    or score-based.

    When ``dissent`` (list of ``{personality, chose}``) or ``abstained``
    (list of ``{name, reason}``) is provided, applies a penalty when
    Sentinel — the conservative voice — is the dissenter/abstainer. Other
    personalities' dissent/abstain doesn't change confidence; the spec
    flags Sentinel involvement as semantically stronger.
    """
    if pattern not in VOTE_PATTERN_CONFIDENCE:
        raise ValueError(f"unknown vote pattern: {pattern!r}")
    conf = VOTE_PATTERN_CONFIDENCE[pattern]
    if pattern == "3-0":
        agreement = 1.0
    elif pattern in ("2-1", "2-0"):
        agreement = 2 / 3
    else:
        agreement = 0.0

    notes: list[str] = []
    if conf is not None:
        sentinel_dissenting = pattern == "2-1" and _sentinel_involved(
            dissent, "personality"
        )
        sentinel_abstaining = pattern == "2-0" and _sentinel_involved(
            abstained, "name"
        )
        if sentinel_dissenting:
            conf = round(conf - SENTINEL_DISSENT_PENALTY, 3)
            notes.append(
                f"sentinel dissented (penalty {SENTINEL_DISSENT_PENALTY})"
            )
        if sentinel_abstaining:
            conf = round(conf - SENTINEL_ABSTAIN_PENALTY, 3)
            notes.append(
                f"sentinel abstained (penalty {SENTINEL_ABSTAIN_PENALTY})"
            )

    result = {
        "confidence": conf,
        "agreement": agreement,
        "separation": None,
        "source": "vote_pattern",
    }
    if notes:
        result["notes"] = notes
    return result


def _utility_vec(scores: dict) -> list[float]:
    """Project the three voices onto a common [0,1] = good axis."""
    return [
        float(scores["generator"]),
        float(scores["control"]),
        1.0 - float(scores["conservator"]),
    ]


def _utility(scores: dict) -> float:
    return statistics.fmean(_utility_vec(scores))


def _spread(scores: dict) -> float:
    return statistics.pstdev(_utility_vec(scores))


def validate_input(data: dict) -> None:
    """Validate confidence.py input shape before any computation."""
    validate_keys(data, ["candidates", "chosen"], context="confidence input")
    if not isinstance(data["candidates"], list):
        print("confidence input: 'candidates' must be a list", file=sys.stderr)
        sys.exit(1)
    for i, cand in enumerate(data["candidates"]):
        if not isinstance(cand, dict):
            print(
                f"confidence input: candidates[{i}] must be an object",
                file=sys.stderr,
            )
            sys.exit(1)
        if "scores" not in cand:
            print(
                f"confidence input: candidates[{i}] "
                f"(id={cand.get('id', '?')!r}) "
                f"missing required field 'scores'. "
                f"For Trias mode, pass {{\"vote_pattern\": \"2-1\"}} instead "
                f"of candidates with scores "
                f"(or pipe aggregator --scheme team_vote output directly to "
                f"confidence.py).",
                file=sys.stderr,
            )
            sys.exit(1)
        validate_keys(
            cand["scores"],
            ["generator", "control", "conservator"],
            context=f"candidates[{i}].scores",
        )
        for voice in VOICES:
            try:
                v = float(cand["scores"][voice])
            except (TypeError, ValueError):
                raise ValueError(
                    f"confidence input: candidates[{i}].scores.{voice} "
                    f"is not numeric"
                )
            if not (0.0 <= v <= 1.0):
                raise ValueError(
                    f"confidence input: candidates[{i}].scores.{voice} = "
                    f"{v} is out of range [0, 1]"
                )


def derive(candidates: list[dict], chosen: str | None) -> dict:
    if chosen is None:
        return {
            "confidence": None,
            "reason": "no chosen candidate (e.g. all vetoed)",
        }

    by_id = {c["id"]: c for c in candidates}
    if chosen not in by_id:
        return {
            "confidence": None,
            "reason": f"chosen={chosen!r} not in candidates",
        }

    chosen_c = by_id[chosen]
    agreement = 1.0 - (_spread(chosen_c["scores"]) / MAX_STDEV_3VALS)
    agreement = max(0.0, min(1.0, agreement))

    others = [c for c in candidates if c["id"] != chosen]
    if others:
        chosen_u = _utility(chosen_c["scores"])
        runner_up_u = max(_utility(c["scores"]) for c in others)
        separation = max(0.0, chosen_u - runner_up_u)
    else:
        separation = 1.0

    raw = AGREEMENT_WEIGHT * agreement + SEPARATION_WEIGHT * separation
    confidence = max(CONFIDENCE_FLOOR, min(CONFIDENCE_CEIL, raw))

    return {
        "confidence": round(confidence, 3),
        "agreement": round(agreement, 3),
        "separation": round(separation, 3),
    }


def main(argv: list[str] | None = None) -> int:
    force_utf8_streams()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input",
        type=argparse.FileType("r", encoding="utf-8-sig"),
        default=sys.stdin,
        help="JSON input file (default: stdin)",
    )
    args = ap.parse_args(argv)

    # Clean exit on malformed/BOM-prefixed input, matching the sibling pipeline
    # scripts (build_report.py / validate_report.py exit 2 on JSONDecodeError).
    # PowerShell 5.1 pipes prepend a BOM on stdin — strip it before parsing.
    try:
        data = json.loads(args.input.read().lstrip("﻿"))
    except json.JSONDecodeError as exc:
        print(f"confidence: invalid JSON input: {exc}", file=sys.stderr)
        return 2

    # Trias mode: when vote_pattern is present, derive confidence from pattern
    # instead of from utility/variance over voice scores. Dissent/abstained
    # arrive on aggregator output piped from --scheme team_vote.
    if "vote_pattern" in data:
        # Same clean-exit contract as the score path below: an unknown
        # pattern (e.g. "3-0-0") raises ValueError in
        # confidence_from_vote_pattern — catch it so the caller gets a
        # one-line stderr message, not a raw traceback.
        try:
            result = confidence_from_vote_pattern(
                data["vote_pattern"],
                dissent=data.get("dissent"),
                abstained=data.get("abstained"),
            )
        except ValueError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    try:
        validate_input(data)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    result = derive(data.get("candidates", []), data.get("chosen"))
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
