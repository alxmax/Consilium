#!/usr/bin/env python
"""Contract test for the 2026-06-19 Trias skeptic-lever redesign (6->4).

The Trias skeptic stage is orchestrator prose in modes/trias.md, not a script
function — so the guard against a silent regression is a contract test over the
spec itself. It asserts the redesign's load-bearing elements survive any future
edit (review 2026-06-19 audit, Reviewer 6 blocking: "a targeted test gated in CI").

Run: python -X utf8 scripts/test_trias_skeptic_lever.py    (exit 0 = pass)
"""
# tested-by: CONSILIUM-MODE-TRIAS-001
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent / "consilium"  # the shipped plugin (SKILL.md, modes/, prompts/, scripts/)
TRIAS = (REPO / "modes" / "trias.md").read_text(encoding="utf-8")

_fails: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _fails.append(name)


def _frontmatter(field: str) -> str | None:
    m = re.search(rf"^{re.escape(field)}:\s*(.+)$", TRIAS, re.MULTILINE)
    return m.group(1).strip() if m else None


def test_frontmatter_counts() -> None:
    check("frontmatter subagents == 4", _frontmatter("subagents") == "4")
    check("frontmatter cost_multiplier == 2.67", _frontmatter("cost_multiplier") == "2.67")
    check("frontmatter dispatch_count_worst_case == 7", _frontmatter("dispatch_count_worst_case") == "7")


def test_post_vote_single_skeptic() -> None:
    check("spec describes ONE post-vote skeptic_on_chosen",
          "skeptic_on_chosen" in TRIAS and "post-vote" in TRIAS.lower())
    check("pre-vote per-personality Skeptic stage is removed (Step 3.5 = no pre-vote Skeptic)",
          "No pre-vote Skeptic" in TRIAS or "no pre-vote Skeptic" in TRIAS)


def test_demolish_predicate_is_concrete() -> None:
    # "demolishes" must be bound to a concrete predicate (Reviewer 1 blocking).
    # 2026-07-02: re-keyed from the phantom `severity == "blocking"` (a field
    # skeptic.md never emits) to `addressable == "requires_redesign"`, aligning
    # with the --skeptic-can-override table in modes/skeptic_on_chosen.md.
    check("demolish predicate references addressable == requires_redesign",
          re.search(r'addressable\s*==\s*"requires_redesign"', TRIAS) is not None)
    check("phantom severity == blocking predicate is gone",
          re.search(r'severity\s*==\s*"blocking"', TRIAS) is None)


def test_override_revote_safety() -> None:
    # Override re-vote must not silently promote an unscrutinised candidate (Reviewer 4/Reviewer 6 blocking).
    check("override re-vote is gated on --skeptic-can-override",
          "--skeptic-can-override" in TRIAS)
    check("re-elected winner is itself re-challenged (no silent promotion)",
          "skeptic_challenges_count: 2" in TRIAS)


def test_default_a_with_c_flag() -> None:
    check("default policy is unconditional (Variant A)",
          "Default policy is unconditional" in TRIAS or "default-A" in TRIAS.lower() or "Default-A" in TRIAS)
    check("Variant-C confidence gate is opt-in (off by default)",
          "--trias-skeptic-gate" in TRIAS and "off by default" in TRIAS)


def test_telemetry_fields_documented() -> None:
    check("records skeptic_challenges_count", "skeptic_challenges_count" in TRIAS)
    check("records post_vote_skeptic_used", "post_vote_skeptic_used" in TRIAS)


def test_t1_debt_booked() -> None:
    check("T1 coverage debt is flagged as unvalidated",
          "T1 coverage debt" in TRIAS or "unvalidated" in TRIAS.lower())


def test_parallel_preserved() -> None:
    # The cost lever is the Skeptic count, NOT the personality topology — parallel stays.
    check("personalities stay blind + parallel",
          "blind + parallel" in TRIAS or "blind & parallel" in TRIAS)


def main() -> int:
    print("test_trias_skeptic_lever")
    for fn in [test_frontmatter_counts, test_post_vote_single_skeptic,
               test_demolish_predicate_is_concrete, test_override_revote_safety,
               test_default_a_with_c_flag, test_telemetry_fields_documented,
               test_t1_debt_booked, test_parallel_preserved]:
        fn()
    print(f"\n{'OK' if not _fails else 'FAILED: ' + ', '.join(_fails)}")
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
