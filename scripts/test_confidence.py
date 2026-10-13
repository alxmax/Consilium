"""Tests for confidence derivation from voice-score variance and vote patterns.

Covers both score-based mode (sequential/dialectic) and Trias mode (democratic
vote pattern). Includes agreement calculation, separation signal blending,
mode-floor exemption logic, and Sentinel-specific dissent/abstain penalties.

Run:
    python scripts/test_confidence.py
    python -m pytest scripts/test_confidence.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-CONFIDENCE-001
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from confidence import (
    check_mode_floor,
    confidence_from_vote_pattern,
    derive,
    validate_input,
    CONFIDENCE_CEIL,
    CONFIDENCE_FLOOR,
    SENTINEL_ABSTAIN_PENALTY,
    SENTINEL_DISSENT_PENALTY,
    VOTE_PATTERN_CONFIDENCE,
)


class TestDeriveScoreBased(unittest.TestCase):
    def test_high_agreement_near_perfect_confidence(self):
        candidates = [
            {"id": "chosen", "scores": {"generator": 0.8, "control": 0.9, "conservator": 0.1}}
        ]
        result = derive(candidates, "chosen")
        self.assertIsNotNone(result["confidence"])
        self.assertGreater(result["confidence"], 0.90)
        self.assertLessEqual(result["confidence"], CONFIDENCE_CEIL)

    def test_no_separation_when_only_chosen(self):
        candidates = [
            {"id": "only_one", "scores": {"generator": 0.5, "control": 0.5, "conservator": 0.5}}
        ]
        result = derive(candidates, "only_one")
        self.assertEqual(result["separation"], 1.0)

    def test_separation_present_with_runner_up(self):
        candidates = [
            {"id": "chosen", "scores": {"generator": 0.9, "control": 0.9, "conservator": 0.1}},
            {"id": "runnerup", "scores": {"generator": 0.5, "control": 0.5, "conservator": 0.5}},
        ]
        result = derive(candidates, "chosen")
        self.assertGreater(result["separation"], 0.0)
        self.assertLess(result["separation"], 1.0)

    def test_chosen_not_in_candidates(self):
        candidates = [{"id": "A", "scores": {"generator": 0.5, "control": 0.5, "conservator": 0.5}}]
        result = derive(candidates, "nonexistent")
        self.assertIsNone(result["confidence"])
        self.assertIn("reason", result)

    def test_confidence_clamped_floor(self):
        candidates = [
            {"id": "c1", "scores": {"generator": 0.0, "control": 0.0, "conservator": 1.0}},
        ]
        result = derive(candidates, "c1")
        self.assertGreaterEqual(result["confidence"], CONFIDENCE_FLOOR)

    def test_confidence_clamped_ceil(self):
        candidates = [
            {"id": "perfect", "scores": {"generator": 0.5, "control": 0.5, "conservator": 0.5}},
        ]
        result = derive(candidates, "perfect")
        self.assertLessEqual(result["confidence"], CONFIDENCE_CEIL)
        self.assertLess(result["confidence"], 1.0)


class TestDeriveNullChosen(unittest.TestCase):
    def test_none_chosen_returns_null_confidence(self):
        candidates = [{"id": "A", "scores": {"generator": 0.5, "control": 0.5, "conservator": 0.5}}]
        result = derive(candidates, None)
        self.assertIsNone(result["confidence"])
        self.assertIn("reason", result)


class TestValidateInput(unittest.TestCase):
    def test_valid_input_passes(self):
        data = {
            "candidates": [{"id": "A", "scores": {"generator": 0.5, "control": 0.5, "conservator": 0.5}}],
            "chosen": "A",
        }
        try:
            validate_input(data)
        except SystemExit:
            self.fail("validate_input raised SystemExit for valid input")

    def test_missing_scores_key_exits_1(self):
        data = {
            "candidates": [{"id": "A"}],
            "chosen": "A",
        }
        with self.assertRaises(SystemExit) as ctx:
            validate_input(data)
        self.assertEqual(ctx.exception.code, 1)


class TestTriasVotePattern(unittest.TestCase):
    def test_three_zero_unanimous(self):
        result = confidence_from_vote_pattern("3-0")
        self.assertEqual(result["confidence"], VOTE_PATTERN_CONFIDENCE["3-0"])
        self.assertEqual(result["agreement"], 1.0)
        self.assertIsNone(result["separation"])
        self.assertEqual(result["source"], "vote_pattern")

    def test_two_one_dissent_without_steward(self):
        result = confidence_from_vote_pattern(
            "2-1",
            dissent=[{"personality": "essentialist", "chose": "other"}],
        )
        self.assertEqual(result["confidence"], VOTE_PATTERN_CONFIDENCE["2-1"])

    def test_two_one_dissent_with_steward(self):
        result = confidence_from_vote_pattern(
            "2-1",
            dissent=[{"personality": "sentinel", "chose": "other"}],
        )
        expected = round(VOTE_PATTERN_CONFIDENCE["2-1"] - SENTINEL_DISSENT_PENALTY, 3)
        self.assertEqual(result["confidence"], expected)

    def test_two_zero_veto(self):
        result = confidence_from_vote_pattern("2-0")
        self.assertEqual(result["confidence"], VOTE_PATTERN_CONFIDENCE["2-0"])

    def test_two_zero_abstain_with_steward(self):
        result = confidence_from_vote_pattern(
            "2-0",
            abstained=[{"name": "sentinel", "reason": "ambiguous"}],
        )
        expected = round(VOTE_PATTERN_CONFIDENCE["2-0"] - SENTINEL_ABSTAIN_PENALTY, 3)
        self.assertEqual(result["confidence"], expected)

    def test_unknown_pattern_raises(self):
        with self.assertRaises((ValueError, KeyError)):
            confidence_from_vote_pattern("9-9")


class TestCheckModeFloor(unittest.TestCase):
    def test_below_floor_flagged(self):
        result = check_mode_floor("trias", 0.70)
        self.assertTrue(result["below_floor"])

    def test_above_floor_ok(self):
        result = check_mode_floor("trias", 0.95)
        self.assertFalse(result["below_floor"])

    def test_none_confidence_always_ok(self):
        result = check_mode_floor("trias", None)
        self.assertFalse(result["below_floor"])

    def test_unknown_mode_no_floor(self):
        result = check_mode_floor("unknown_mode", 0.5)
        self.assertFalse(result["below_floor"])

    def test_trias_3_0_exempt_from_weak(self):
        result = check_mode_floor("trias", 0.70, vote_pattern="3-0")
        self.assertFalse(result["below_floor"])

    def test_trias_2_1_exempt_from_weak(self):
        result = check_mode_floor("trias", 0.70, vote_pattern="2-1")
        self.assertFalse(result["below_floor"])


class TestModeFloorCompleteness(unittest.TestCase):
    """Guard against partial confidence_floor loss silently disabling the WEAK floor.

    _load_mode_floors() only falls back to _FLOOR_FALLBACK when NO mode declares a
    floor. If a single modes/<mode>.md loses its `confidence_floor:` frontmatter, the
    returned dict is partial and check_mode_floor() returns below_floor=False for the
    missing mode — silently disabling its WEAK floor. The on-disk modes/*.md must
    therefore reproduce _FLOOR_FALLBACK exactly; check_doc_drift enforces the same
    invariant as a CI gate (check_confidence_floor_completeness).
    """

    def test_loaded_floors_equal_fallback(self):
        import confidence
        self.assertEqual(
            dict(confidence.MODE_CONFIDENCE_FLOOR),
            dict(confidence._FLOOR_FALLBACK),
        )

    def test_every_fallback_mode_floor_is_enforced(self):
        # End-to-end: each canonical mode must carry a floor that check_mode_floor
        # actually enforces. A partial loss drops the mode from MODE_CONFIDENCE_FLOOR,
        # so check_mode_floor(mode, floor-0.01) would return below_floor=False here.
        import confidence
        for mode, floor in confidence._FLOOR_FALLBACK.items():
            res = check_mode_floor(mode, round(floor - 0.01, 3))
            self.assertTrue(res["below_floor"], f"{mode}: WEAK floor not enforced")

    # RED-path coverage for the check_doc_drift invariant itself. A live (green-repo)
    # check_doc_drift run only exercises the pass path; without these, a regression that
    # makes _confidence_floor_failures never fire would ship silently (skeptic 2026-06-29).

    def test_floor_failures_helper_detects_every_drift_kind(self):
        from check_doc_drift import _confidence_floor_failures
        base = {"sequential": 0.70, "dialectic": 0.75, "trias": 0.80}
        self.assertEqual(_confidence_floor_failures(dict(base), dict(base)), [])
        # missing — a mode dropped its confidence_floor (the partial-loss bug)
        partial = {k: v for k, v in base.items() if k != "trias"}
        miss = _confidence_floor_failures(partial, base)
        self.assertTrue(miss and "trias" in miss[0], miss)
        # mismatched — a floor drifted to a different value
        mism = _confidence_floor_failures({**base, "trias": 0.50}, base)
        self.assertTrue(mism and "trias" in mism[0], mism)
        # unexpected — a floor present that the fallback does not declare
        extra = _confidence_floor_failures({**base, "ghost": 0.99}, base)
        self.assertTrue(extra and "ghost" in extra[0], extra)

    def test_completeness_check_passes_on_repo(self):
        from check_doc_drift import check_confidence_floor_completeness
        self.assertEqual(check_confidence_floor_completeness(), [])

    def test_completeness_check_fires_on_partial_loss(self):
        # End-to-end failure branch: point the checker at a modes/ dir where trias.md
        # has lost its confidence_floor; the invariant reads frontmatter directly, so it
        # must fire and name trias. (The real modes/*.md are correctly complete.)
        import confidence
        from check_doc_drift import check_confidence_floor_completeness
        original = confidence._MODES_DIR
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / "sequential.md").write_text(
                "---\nname: sequential\nconfidence_floor: 0.70\n---\n", encoding="utf-8")
            (tmp / "dialectic.md").write_text(
                "---\nname: dialectic\nconfidence_floor: 0.75\n---\n", encoding="utf-8")
            (tmp / "trias.md").write_text(
                "---\nname: trias\n---\n", encoding="utf-8")  # floor stripped
            confidence._MODES_DIR = tmp
            try:
                failures = check_confidence_floor_completeness()
            finally:
                confidence._MODES_DIR = original
        self.assertTrue(failures, "completeness check did not fire on partial floor loss")
        self.assertIn("trias", failures[0])

    def test_completeness_check_fires_when_modes_absent(self):
        # review 2026-06-29 (Reviewer 6): when modes/ is absent the runtime loader collapses to
        # _FLOOR_FALLBACK, so comparing the loaded dict to the fallback would tautologically
        # pass. The direct-read check must instead FAIL LOUD — a drift-checker may not
        # silently certify "no drift" when it could not read the source of truth.
        import confidence
        from check_doc_drift import check_confidence_floor_completeness
        original = confidence._MODES_DIR
        with tempfile.TemporaryDirectory() as d:
            confidence._MODES_DIR = Path(d) / "does_not_exist"
            try:
                failures = check_confidence_floor_completeness()
            finally:
                confidence._MODES_DIR = original
        self.assertTrue(failures, "completeness check did not fire when modes/ absent")
        self.assertIn("modes/", failures[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
