"""Tests for log_feedback.py pure functions.

Covers fingerprinting, string cleaning/truncation, note derivation,
and entry assembly — the deterministic surface of the feedback logger.

Run:
    python scripts/test_log_feedback.py
    python -m pytest scripts/test_log_feedback.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-LOG-FEEDBACK-001
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from log_feedback import _fingerprint, _clean, truncate, derive_note, build_entry


class TestFingerprint(unittest.TestCase):
    def test_deterministic(self):
        # Without run_id, _fingerprint uses microseconds → intentionally non-deterministic.
        # With run_id it is sha256-based and stable across calls.
        fp1 = _fingerprint("2026-05-12", "approach_a", "test context", run_id="2026-05-12_r.json")
        fp2 = _fingerprint("2026-05-12", "approach_a", "test context", run_id="2026-05-12_r.json")
        self.assertEqual(fp1, fp2)

    def test_changes_with_run_id(self):
        # Different run_ids must produce different fingerprints.
        fp1 = _fingerprint("2026-05-12", "approach_a", "context", run_id="2026-05-12_a.json")
        fp2 = _fingerprint("2026-05-12", "approach_a", "context", run_id="2026-05-12_b.json")
        self.assertNotEqual(fp1, fp2)

    def test_length_is_16(self):
        fp = _fingerprint("2026-05-12", "a", "b")
        self.assertEqual(len(fp), 16)

    def test_changes_with_different_inputs(self):
        fp1 = _fingerprint("2026-01-01", "approach_a", "ctx")
        fp2 = _fingerprint("2026-01-02", "approach_a", "ctx")
        self.assertNotEqual(fp1, fp2)


class TestClean(unittest.TestCase):
    def test_replaces_pipes_with_slashes(self):
        self.assertEqual(_clean("foo|bar|baz"), "foo/bar/baz")

    def test_replaces_newlines_with_spaces(self):
        result = _clean("line1\nline2")
        self.assertEqual(result, "line1 line2")

    def test_strips_whitespace(self):
        self.assertEqual(_clean("  text  "), "text")

    def test_combines_all(self):
        self.assertEqual(_clean("  foo|bar\nqux  "), "foo/bar qux")


class TestTruncate(unittest.TestCase):
    def test_no_truncation_when_within_limit(self):
        self.assertEqual(truncate("short", 10), "short")

    def test_adds_ellipsis_when_over(self):
        result = truncate("a" * 15, 10)
        self.assertEqual(len(result), 10)
        self.assertTrue(result.endswith("…"))

    def test_never_exceeds_limit(self):
        for n in [5, 10, 20, 60]:
            result = truncate("x" * 100, n)
            self.assertLessEqual(len(result), n)


class TestDeriveNote(unittest.TestCase):
    def test_skipped_report(self):
        report = {"skipped": True, "skip_reason": "test skip"}
        result = derive_note(report)
        self.assertIn("skip", result.lower())

    def test_all_vetoed(self):
        report = {
            "chosen_approach": None,
            "deliberation_log": [
                {"step": "aggregate", "result": {"retry_suggested": {"relaxed_threshold": 0.55}}}
            ],
        }
        result = derive_note(report)
        self.assertIn("veto", result.lower())

    def test_normal_report(self):
        report = {
            "chosen_approach": "approach_a",
            "confidence": 0.85,
            "deliberation_log": [
                {"step": "generator", "candidates": ["a", "b", "c"]},
                {"step": "aggregate", "result": {"vetoed": ["b"]}},
            ],
            "telemetry": {"mode": "sequential"},
        }
        result = derive_note(report)
        self.assertIn("0.85", result)


class TestBuildEntry(unittest.TestCase):
    def _base_report(self, **overrides):
        base = {
            "success_criterion": "test criterion",
            "chosen_approach": "my_approach",
            "deliberation_log": [
                {"step": "generator", "candidates": []},
                {"step": "aggregate", "result": {"vetoed": []}},
            ],
        }
        base.update(overrides)
        return base

    def test_requires_success_criterion(self):
        with self.assertRaises((ValueError, SystemExit)):
            build_entry({"chosen_approach": "foo"})

    def test_requires_chosen_approach(self):
        with self.assertRaises((ValueError, SystemExit)):
            build_entry({"success_criterion": "test"})

    def test_default_outcome_is_pend(self):
        entry = build_entry(self._base_report())
        self.assertEqual(entry["outcome"], "PEND")

    def test_respects_provided_outcome(self):
        entry = build_entry(self._base_report(), outcome="BAD")
        self.assertEqual(entry["outcome"], "BAD")

    def test_ovr_requires_override_target(self):
        with self.assertRaises((ValueError, SystemExit)):
            build_entry(self._base_report(), outcome="OVR")

    def test_ovr_with_override_target_adds_note(self):
        entry = build_entry(self._base_report(), outcome="OVR", override_target="alt_b")
        self.assertIn("alt_b", entry["note"])

    def test_user_note_appended(self):
        entry = build_entry(self._base_report(), user_note="my feedback")
        self.assertIn("my feedback", entry["note"])

    def test_date_is_iso_format(self):
        entry = build_entry(self._base_report())
        self.assertRegex(entry["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_context_truncated(self):
        entry = build_entry(self._base_report(success_criterion="x" * 200))
        self.assertLessEqual(len(entry["context"]), 70)

    def test_null_chosen_becomes_string(self):
        report = self._base_report(
            chosen_approach=None,
            deliberation_log=[
                {"step": "aggregate", "result": {"retry_suggested": {"relaxed_threshold": 0.5}}}
            ],
        )
        entry = build_entry(report)
        self.assertEqual(entry["chosen"], "null")


if __name__ == "__main__":
    unittest.main(verbosity=2)
