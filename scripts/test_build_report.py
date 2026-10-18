"""Tests for the canonical deliberation report assembly module.

Covers the build_report pipeline: accepting intermediate voice/aggregation outputs
and emitting the canonical report shape with proper voice scores, alternatives,
deliberation log, and version provenance.

Run:
    python scripts/test_build_report.py
    python -m pytest scripts/test_build_report.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-BUILD-REPORT-001
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from build_report import (
    build,
    validate_input,
    _voice_scores_for,
    _why_not,
    _alternatives,
    _stamp_provenance,
    _conservator_risk,
    _candidate_by_id,
)


class TestValidateInput(unittest.TestCase):
    def test_normal_bundle_requires_five_keys(self):
        valid = {
            "success_criterion": "test",
            "verification": "test",
            "generator": {},
            "control": {},
            "conservator": {},
        }
        validate_input(valid)

    def test_skipped_bundle_requires_two_keys(self):
        valid = {
            "skipped": True,
            "success_criterion": "test",
            "verification": "test",
        }
        validate_input(valid)

    def test_missing_success_criterion_raises(self):
        invalid = {"verification": "test", "generator": {}, "control": {}, "conservator": {}}
        with self.assertRaises((ValueError, SystemExit)):
            validate_input(invalid)

    def test_missing_verification_raises(self):
        invalid = {"success_criterion": "test", "generator": {}, "control": {}, "conservator": {}}
        with self.assertRaises((ValueError, SystemExit)):
            validate_input(invalid)

    def test_normal_bundle_missing_generator_raises(self):
        invalid = {"success_criterion": "test", "verification": "test", "control": {}, "conservator": {}}
        with self.assertRaises((ValueError, SystemExit)):
            validate_input(invalid)


class TestBuildSkipped(unittest.TestCase):
    def test_skipped_bundle_sets_pipeline_executed_false(self):
        bundle = {
            "skipped": True,
            "success_criterion": "test",
            "verification": "verify",
            "skip_reason": "trivial-direct",
            "signals": {},
        }
        report = build(bundle)
        pipeline = report.get("pipeline_executed", False)
        self.assertFalse(pipeline)

    def test_skipped_bundle_chosen_approach_is_skipped(self):
        bundle = {
            "skipped": True,
            "success_criterion": "test",
            "verification": "verify",
            "skip_reason": "prior-deliberation",
            "signals": {"foo": "bar"},
        }
        report = build(bundle)
        self.assertEqual(report["chosen_approach"], "skipped")

    def test_skipped_bundle_empty_deliberation_log(self):
        bundle = {
            "skipped": True,
            "success_criterion": "test",
            "verification": "verify",
            "skip_reason": "test",
        }
        report = build(bundle)
        self.assertEqual(report["deliberation_log"], [])


class TestBuildFull(unittest.TestCase):
    def _base_bundle(self, **overrides):
        base = {
            "success_criterion": "test criterion",
            "verification": "test verification",
            "generator": {
                "candidates": [{"id": "A", "summary": "Option A"}]
            },
            "control": {
                "verdicts": [{"id": "A", "valid": True, "issues": []}]
            },
            "conservator": {
                "scores": [{"id": "A", "regression_risk": {"net_concern": 0.1}}]
            },
            "aggregate": {"chosen": "A", "scheme": "sequential"},
            "confidence": {"confidence": 0.85},
        }
        base.update(overrides)
        return base

    def test_full_bundle_pipeline_executed_true(self):
        report = build(self._base_bundle())
        self.assertTrue(report["pipeline_executed"])

    def test_full_bundle_deliberation_log_four_steps(self):
        report = build(self._base_bundle())
        self.assertEqual(len(report["deliberation_log"]), 4)
        steps = [step["step"] for step in report["deliberation_log"]]
        self.assertEqual(steps, ["generator", "control", "conservator", "aggregate"])

    def test_telemetry_without_dispatch_count_or_latency_is_marked_incomplete(self):
        report = build(self._base_bundle(telemetry={"mode": "sequential"}))
        self.assertIs(report.get("telemetry_incomplete"), True)
        self.assertEqual(report["telemetry_gaps"], ["dispatch_count", "latency_ms"])

    def test_zero_latency_counts_as_unmeasured(self):
        tele = {"mode": "sequential", "dispatch_count": 3,
                "voices": {"generator": {"tokens_in": 1, "tokens_out": 1,
                                         "latency_ms": 0}}}
        report = build(self._base_bundle(telemetry=tele))
        self.assertEqual(report["telemetry_gaps"], ["latency_ms"])

    def test_complete_telemetry_is_not_marked(self):
        tele = {"mode": "sequential", "dispatch_count": 3,
                "voices": {"generator": {"tokens_in": 10, "tokens_out": 5,
                                         "latency_ms": 1200}}}
        report = build(self._base_bundle(telemetry=tele))
        self.assertNotIn("telemetry_incomplete", report)
        self.assertNotIn("telemetry_gaps", report)

    def test_top_level_latency_also_counts_as_measured(self):
        tele = {"mode": "sequential", "dispatch_count": 3, "latency_ms": 900}
        report = build(self._base_bundle(telemetry=tele))
        self.assertNotIn("telemetry_incomplete", report)

    def test_skipped_report_is_never_marked(self):
        report = build({"success_criterion": "c", "verification": "v",
                        "skipped": True, "skip_reason": "trivial"})
        self.assertNotIn("telemetry_incomplete", report)

    def test_full_bundle_chosen_approach_set(self):
        report = build(self._base_bundle())
        self.assertEqual(report["chosen_approach"], "A")

    def test_chosen_none_allowed(self):
        report = build(self._base_bundle(aggregate={"chosen": None, "scheme": "sequential"}))
        self.assertIsNone(report["chosen_approach"])

    def test_control_step_passes_through_strongest_objection(self):
        bundle = self._base_bundle(control={
            "verdicts": [{"id": "A", "valid": True, "issues": []}],
            "strongest_objection": {"target_id": None,
                                    "reason": "wrong if weekly transactions < 40 for 4 weeks"},
            "no_blocking_defect_attested": True,
        })
        report = build(bundle)
        control_step = next(s for s in report["deliberation_log"] if s["step"] == "control")
        self.assertEqual(control_step["strongest_objection"]["reason"],
                         "wrong if weekly transactions < 40 for 4 weeks")
        self.assertTrue(control_step["no_blocking_defect_attested"])

    def test_control_step_omits_strongest_objection_when_absent(self):
        report = build(self._base_bundle())
        control_step = next(s for s in report["deliberation_log"] if s["step"] == "control")
        self.assertNotIn("strongest_objection", control_step)
        self.assertNotIn("no_blocking_defect_attested", control_step)


class TestVoiceScores(unittest.TestCase):
    def test_voice_scores_for_chosen_candidate(self):
        control = {"verdicts": [{"id": "A", "valid": True, "issues": []}]}
        conservator = {"scores": [{"id": "A", "regression_risk": {"net_concern": 0.25}}]}
        scores = _voice_scores_for("A", control, conservator)
        self.assertIsNotNone(scores)
        assert scores is not None
        self.assertIn("control", scores)
        self.assertIn("conservator", scores)
        self.assertIn("generator", scores)
        self.assertEqual(scores["conservator"], 0.25)

    def test_voice_scores_returns_none_for_none_chosen(self):
        scores = _voice_scores_for(None, {"verdicts": []}, {"scores": []})
        self.assertIsNone(scores)

    def test_control_score_invalid_verdict(self):
        control = {"verdicts": [{"id": "A", "valid": False, "issues": []}]}
        conservator = {"scores": [{"id": "A"}]}
        scores = _voice_scores_for("A", control, conservator)
        assert scores is not None
        self.assertEqual(scores["control"], 0.0)

    def test_generator_score_do_nothing(self):
        control = {"verdicts": [{"id": "do_nothing", "valid": True, "issues": []}]}
        conservator = {"scores": [{"id": "do_nothing"}]}
        scores = _voice_scores_for("do_nothing", control, conservator)
        assert scores is not None
        self.assertEqual(scores["generator"], 0.5)

    def test_generator_score_normal(self):
        control = {"verdicts": [{"id": "A", "valid": True, "issues": []}]}
        conservator = {"scores": [{"id": "A"}]}
        scores = _voice_scores_for("A", control, conservator)
        assert scores is not None
        self.assertEqual(scores["generator"], 1.0)

    def test_conservator_score_missing(self):
        control = {"verdicts": [{"id": "A", "valid": True, "issues": []}]}
        conservator = {"scores": [{"id": "A"}]}
        scores = _voice_scores_for("A", control, conservator)
        assert scores is not None
        self.assertEqual(scores["conservator"], 0.5)


class TestWhyNot(unittest.TestCase):
    def test_why_not_invalid_verdict(self):
        verdict = {"valid": False, "issues": [{"category": "logic"}]}
        result = _why_not(verdict, None)
        self.assertIn("invalid", result)

    def test_why_not_high_risk(self):
        score = {"regression_risk": {"net_concern": 0.6}}
        result = _why_not(None, score)
        self.assertIn("risk=", result)

    def test_why_not_fallback_ranked_below(self):
        result = _why_not(None, None, no_chosen=False)
        self.assertEqual(result, "ranked below chosen")

    def test_why_not_fallback_all_vetoed(self):
        result = _why_not(None, None, no_chosen=True)
        self.assertEqual(result, "all candidates vetoed")


class TestAlternatives(unittest.TestCase):
    def test_alternatives_excludes_chosen(self):
        generator = {"candidates": [{"id": "A"}, {"id": "B"}, {"id": "C"}]}
        alts = _alternatives(generator, {"verdicts": []}, {"scores": []}, {"chosen": "A"}, 3)
        ids = [a["id"] for a in alts]
        self.assertNotIn("A", ids)
        self.assertIn("B", ids)

    def test_alternatives_respects_limit(self):
        generator = {"candidates": [{"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}]}
        alts = _alternatives(generator, {"verdicts": []}, {"scores": []}, {"chosen": "A"}, 2)
        self.assertEqual(len(alts), 2)

    def test_alternatives_zero_limit(self):
        generator = {"candidates": [{"id": "A"}, {"id": "B"}]}
        alts = _alternatives(generator, {"verdicts": []}, {"scores": []}, {"chosen": "A"}, 0)
        self.assertEqual(alts, [])

    def test_alternatives_includes_why_not(self):
        generator = {"candidates": [{"id": "A"}, {"id": "B"}]}
        control = {"verdicts": [{"id": "B", "valid": False, "issues": []}]}
        alts = _alternatives(generator, control, {"scores": []}, {"chosen": "A"}, 1)
        self.assertEqual(len(alts), 1)
        self.assertIn("why_not", alts[0])


class TestConservatorRisk(unittest.TestCase):
    def test_conservator_risk_from_regression_risk_net_concern(self):
        score = {"regression_risk": {"net_concern": 0.42}}
        self.assertEqual(_conservator_risk(score), 0.42)

    def test_conservator_risk_legacy_risk_score(self):
        score = {"risk_score": 0.33}
        self.assertEqual(_conservator_risk(score), 0.33)

    def test_conservator_risk_missing_returns_none(self):
        self.assertIsNone(_conservator_risk({}))

    def test_conservator_risk_prefers_new_schema(self):
        score = {"regression_risk": {"net_concern": 0.5}, "risk_score": 0.3}
        self.assertEqual(_conservator_risk(score), 0.5)


class TestCandidateById(unittest.TestCase):
    def test_find_candidate_by_id(self):
        items = [{"id": "A", "name": "Alice"}, {"id": "B", "name": "Bob"}]
        result = _candidate_by_id(items, "A")
        assert result is not None
        self.assertEqual(result["name"], "Alice")

    def test_candidate_not_found_returns_none(self):
        self.assertIsNone(_candidate_by_id([{"id": "A"}], "Z"))

    def test_empty_list_returns_none(self):
        self.assertIsNone(_candidate_by_id([], "A"))


class TestLowConfidenceSuggestion(unittest.TestCase):
    def test_low_confidence_suggestion_never_emitted(self):
        # Regression: old advisory hint must not appear for any confidence/mode
        b = {
            "success_criterion": "test",
            "verification": "verify",
            "generator": {"candidates": [{"id": "A", "summary": "s"}]},
            "control": {"verdicts": [{"id": "A", "valid": True, "issues": []}]},
            "conservator": {"scores": [{"id": "A", "regression_risk": {"net_concern": 0.2}}]},
            "aggregate": {"chosen": "A", "scheme": "sequential"},
            "confidence": {"confidence": 0.40},
            "telemetry": {"mode": "sequential"},
        }
        report = build(b)
        self.assertNotIn("low_confidence_suggestion", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
