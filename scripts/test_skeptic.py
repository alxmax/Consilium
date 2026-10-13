"""Tests for validate_skeptic.py — the executable Skeptic validation gate.

Covers the machine-checkable subset of the prompts/voices/skeptic.md gate:
evidence threshold, failure_mode/addressable whitelists, goal_fit quote guard,
and the can_object=false path.

Run:
    python scripts/test_skeptic.py
    python -m pytest scripts/test_skeptic.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-VALIDATE-SKEPTIC-001
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from validate_skeptic import validate_skeptic


def _objection(**over):
    base = {
        "concrete_concerns": ["Concern A: foo.py crashes on []", "Concern B: bar.py off-by-one"],
        "quoted_scenario": None,
        "failure_mode": "correctness",
        "addressable": "in_place",
    }
    base.update(over)
    return base


class TestAccepts(unittest.TestCase):
    def test_well_formed_two_concerns(self):
        self.assertEqual(validate_skeptic({"can_object": True, "objection": _objection()}), [])

    def test_one_concern_plus_scenario(self):
        obj = _objection(concrete_concerns=["only one"], quoted_scenario="fails when input empty")
        self.assertEqual(validate_skeptic({"can_object": True, "objection": obj}), [])

    def test_can_object_false_null_objection(self):
        self.assertEqual(validate_skeptic({"can_object": False, "objection": None}), [])

    def test_can_object_false_missing_objection(self):
        self.assertEqual(validate_skeptic({"can_object": False}), [])

    def test_goal_fit_with_success_criterion_quote(self):
        obj = _objection(
            failure_mode="goal_fit",
            concrete_concerns=[
                "success_criterion says X but chosen does Y",
                "second concern for evidence",
            ],
        )
        self.assertEqual(validate_skeptic({"can_object": True, "objection": obj}), [])


class TestRejects(unittest.TestCase):
    def test_under_evidenced_one_concern_null_scenario(self):
        obj = _objection(concrete_concerns=["only one"], quoted_scenario=None)
        problems = validate_skeptic({"can_object": True, "objection": obj})
        self.assertTrue(any("not enough evidence" in p for p in problems))

    def test_goal_fit_without_success_criterion_quote(self):
        obj = _objection(
            failure_mode="goal_fit",
            concrete_concerns=["generic concern one", "generic concern two"],
        )
        problems = validate_skeptic({"can_object": True, "objection": obj})
        self.assertTrue(any("goal_fit" in p and "success_criterion" in p for p in problems))

    def test_unknown_failure_mode(self):
        obj = _objection(failure_mode="might_break")
        problems = validate_skeptic({"can_object": True, "objection": obj})
        self.assertTrue(any("failure_mode" in p for p in problems))

    def test_unknown_addressable(self):
        obj = _objection(addressable="maybe")
        problems = validate_skeptic({"can_object": True, "objection": obj})
        self.assertTrue(any("addressable" in p for p in problems))

    def test_can_object_true_without_objection(self):
        problems = validate_skeptic({"can_object": True, "objection": None})
        self.assertTrue(len(problems) >= 1)

    def test_can_object_false_with_populated_objection(self):
        problems = validate_skeptic({"can_object": False, "objection": _objection()})
        self.assertTrue(any("can_object=false" in p for p in problems))

    def test_non_bool_can_object(self):
        problems = validate_skeptic({"can_object": "yes"})
        self.assertTrue(any("can_object" in p for p in problems))

    def test_not_a_dict(self):
        problems = validate_skeptic(["not", "an", "object"])
        self.assertTrue(len(problems) == 1)


class TestTiebreak(unittest.TestCase):
    # B2 cascade tiebreak mode (audit 2026-07-02): the Skeptic returns a
    # selection, not an objection - validate_skeptic must accept the shape
    # defined in prompts/voices/skeptic.md section 'Tiebreak mode'.

    def test_valid_selection(self):
        v = {"tiebreak": {"chosen": "approach_a", "reason": "fewest concrete failure modes"}}
        self.assertEqual(validate_skeptic(v), [])

    def test_null_chosen_abstain(self):
        v = {"tiebreak": {"chosen": None, "reason": "every candidate has a disqualifying flaw"}}
        self.assertEqual(validate_skeptic(v), [])

    def test_missing_reason_rejected(self):
        problems = validate_skeptic({"tiebreak": {"chosen": "a"}})
        self.assertTrue(any("reason" in p for p in problems))

    def test_empty_chosen_rejected(self):
        problems = validate_skeptic({"tiebreak": {"chosen": "", "reason": "r"}})
        self.assertTrue(any("chosen" in p for p in problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)
