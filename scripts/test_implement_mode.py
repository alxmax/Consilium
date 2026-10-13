"""Smoke test for recommend_implement_mode (Step 7 routing gate).

Run: python scripts/test_implement_mode.py   (exit 0 = all pass, 1 = a failure)

Gate contract: pipeline iff the change warrants a `review` step (regression-prone
quadrants); single_shot otherwise. Keyed on reversibility/magnitude, NOT size.
"""
# tested-by: CONSILIUM-INFER-PIPELINE-001
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path
from infer_pipeline import infer_steps, recommend_implement_mode  # noqa: E402


def _report(magnitude: str, reversibility: str, chosen: str = "approach_x") -> dict:
    return {
        "chosen_approach": chosen,
        "deliberation_log": [
            {"step": "conservator", "scores": [
                {"id": chosen, "regression_risk": {"magnitude": magnitude, "reversibility": reversibility}}
            ]}
        ],
    }


CASES = [
    # (magnitude, reversibility, expected_mode)
    ("trivial",  "complete",     "single_shot"),
    ("moderate", "complete",     "single_shot"),
    ("moderate", "partial",      "single_shot"),   # no review in table
    ("moderate", "irreversible", "pipeline"),
    ("high",     "complete",     "single_shot"),   # big but fully reversible -> no regression to catch
    ("high",     "partial",      "pipeline"),
    ("high",     "irreversible", "pipeline"),
    ("critical", "complete",     "pipeline"),
]


def main() -> int:
    passed = failed = 0
    for mag, rev, expected in CASES:
        got = recommend_implement_mode(_report(mag, rev))
        ok = got == expected
        passed += ok
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  ({mag},{rev}) -> {got} (expected {expected})")

    # do_nothing / skipped -> single_shot (no implementation to route)
    for chosen in ("do_nothing", "skipped"):
        got = recommend_implement_mode({"chosen_approach": chosen})
        ok = got == "single_shot"
        passed += ok
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  chosen={chosen} -> {got} (expected single_shot)")

    # Regression: a hand-built report (prior-deliberation passthrough / scale_down)
    # carries voice_scores=null and no conservator scores. infer_steps/recommend_implement_mode
    # must route via the 0.5-net_concern fallback, NOT crash with AttributeError on None.get().
    passthrough = {
        "chosen_approach": "prior-deliberation",
        "voice_scores": None,
        "deliberation_log": [{"step": "prior_deliberation_passthrough", "matched": "x", "date": "2026-05-31"}],
    }
    try:
        steps, _ = infer_steps(passthrough)
        mode = recommend_implement_mode(passthrough)
        ok = isinstance(steps, list) and mode in ("pipeline", "single_shot")
        note = f"steps={steps}, mode={mode}"
    except Exception as exc:  # noqa: BLE001 — the bug under test raised AttributeError
        ok = False
        note = f"raised {type(exc).__name__}: {exc}"
    passed += ok
    failed += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  null voice_scores report does not crash ({note})")

    # Regression (audit 2026-07-02): an explicit conservator score of 0.0 was
    # coerced to 0.5 by `or 0.5` (falsy), mis-routing a zero-concern change to
    # the full pipeline and misreporting the rationale. 0.0 must hit the
    # 'trivial' bucket -> ['implement', 'compile'] -> single_shot.
    zero_concern = {
        "chosen_approach": "a",
        "voice_scores": {"conservator": 0.0},
        "deliberation_log": [],
    }
    try:
        steps, _ = infer_steps(zero_concern)
        mode = recommend_implement_mode(zero_concern)
        ok = steps == ["implement", "compile"] and mode == "single_shot"
        note = f"steps={steps}, mode={mode}"
    except Exception as exc:  # noqa: BLE001
        ok = False
        note = f"raised {type(exc).__name__}: {exc}"
    passed += ok
    failed += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  conservator=0.0 routes single_shot ({note})")

    print(f"\n{passed}/{passed + failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
