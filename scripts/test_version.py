"""Tests for repo version provenance (scripts/version.py) + the report stamp.

Run: python scripts/test_version.py   (exit 0 = all pass, 1 = a failure)

review-mandated coverage (2026-05-31_200016-versioning-provenance-design):
- consilium_version returns a string; FAILS OPEN to "unknown" when git is absent.
- consilium_ref returns "" on a dirty tree / git-absent (Reviewer 1: a
  "<sha>-dirty" string is never recorded as a diff operand).
- prompts_changed_since NEVER raises and returns 0 on ""/"unknown"/unreachable
  refs (Reviewer 6's guard) — so the Step-0 advisory can call it unconditionally.
- All THREE report producers carry the stamp (Reviewer 4): build_report pipeline
  output + the two hand-built SKILL.md templates (scale_down, passthrough).
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "consilium"  # the shipped plugin (SKILL.md, modes/, prompts/, scripts/)
sys.path.insert(0, str(ROOT / "scripts"))
import version  # noqa: E402
from build_report import build  # noqa: E402


def run() -> int:
    passed = failed = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        ok = bool(cond)
        passed += ok
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  -> ' + detail}")

    # 1. version returns a non-empty string on a real repo.
    v = version.consilium_version()
    check("version returns non-empty str", isinstance(v, str) and bool(v), repr(v))

    # 2-5. fail-open + dirty behavior via a stubbed _git (no real git state needed).
    orig = version._git
    try:
        version._git = lambda *_: None  # git absent / every call fails
        check("version == 'unknown' when git absent", version.consilium_version() == "unknown")
        check("ref == '' when git absent", version.consilium_ref() == "")
        check("ref_resolves False when git absent", version.ref_resolves("abc") is False)
        check("prompts_changed_since == 0 when git absent", version.prompts_changed_since("abc") == 0)

        version._git = lambda args: "M somefile" if args[:1] == ["status"] else "abc123"
        check("ref == '' on dirty tree", version.consilium_ref() == "", repr(version.consilium_ref()))

        version._git = lambda args: "" if args[:1] == ["status"] else "abc123def456"
        check("ref == HEAD sha on clean tree", version.consilium_ref() == "abc123def456", repr(version.consilium_ref()))
    finally:
        version._git = orig

    # 6. ref_resolves short-circuits empty/"unknown" to False without a git call.
    check("ref_resolves('') is False", version.ref_resolves("") is False)
    check("ref_resolves('unknown') is False", version.ref_resolves("unknown") is False)

    # 7. prompts_changed_since NEVER raises and returns 0 on bad refs (Reviewer 6's guard).
    for bad in ("", "unknown", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"):
        try:
            n = version.prompts_changed_since(bad)
            ok, detail = (n == 0), f"returned {n}"
        except Exception as exc:  # noqa: BLE001 — the guard under test must prevent this
            ok, detail = False, f"raised {type(exc).__name__}"
        check(f"prompts_changed_since({bad[:10]!r}) -> 0, no raise", ok, detail)
    try:
        n = version.prompts_changed_since("HEAD")
        check("prompts_changed_since('HEAD') -> int >= 0", isinstance(n, int) and n >= 0, str(n))
    except Exception as exc:  # noqa: BLE001
        check("prompts_changed_since('HEAD') no raise", False, type(exc).__name__)

    # 8. Producer 1 — build_report stamps both fields on a normal + skipped report.
    bundle = {
        "success_criterion": "x", "verification": "v",
        "generator": {"candidates": [{"id": "a", "summary": "s"}]},
        "control": {"verdicts": [{"id": "a", "valid": True}]},
        "conservator": {"scores": [{"id": "a", "regression_risk": {"reversibility": "complete", "magnitude": "trivial", "net_concern": 0.1}}]},
        "aggregate": {"scheme": "sequential", "chosen": "a"},
        "confidence": {"confidence": 0.8},
    }
    tele = (build(bundle).get("telemetry") or {})
    check("build_report stamps consilium_version", "consilium_version" in tele, str(tele))
    check("build_report stamps consilium_ref", "consilium_ref" in tele, str(tele))
    sk = (build({"success_criterion": "x", "verification": "v", "skipped": True, "skip_reason": "trivial"}).get("telemetry") or {})
    check("skipped report stamped", "consilium_version" in sk)

    # 9. Producers 2 & 3 — both hand-built SKILL.md templates carry the stamp (Reviewer 4).
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for mode in ("prior_deliberation_passthrough", "sequential_scale_down"):
        line = next((ln for ln in skill.splitlines() if f'"mode": "{mode}"' in ln), "")
        ok = "consilium_version" in line and "consilium_ref" in line
        check(f"SKILL.md template '{mode}' carries the stamp", ok, line[:90])

    print(f"\n{passed}/{passed + failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())

# tested-by: CONSILIUM-VERSION-001
# tested-by: CONSILIUM-BUILD-REPORT-001  (the report-stamp checks: all three producers carry the stamp)
