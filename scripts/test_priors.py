"""Tests for CONSILIUM-PRIORS-001: advisory soft-prior signals from deliberation history.

Covers signal computation: counts, rates (override/bad/weighted), stale pendings,
missing feedback runs, top keywords, prior match, and conservator veto rate.

Run:
    python scripts/test_priors.py
    python -m pytest scripts/test_priors.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-PRIORS-001
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from priors import (
    CONFIRMED_MARKER,
    STALE_PEND_DAYS,
    _find_prior_match,
    _is_confirmed,
    _outcome_counts,
    _rates,
    _top_keywords,
    find_missing_feedback_runs,
    find_stale_pendings,
    parse_runs,
)


class TestOutcomeCounts(unittest.TestCase):
    def test_empty_list(self):
        result = _outcome_counts([])
        self.assertEqual(dict(result), {})

    def test_single_entry(self):
        result = _outcome_counts([{"outcome": "OK"}])
        self.assertEqual(result["OK"], 1)

    def test_mixed_outcomes(self):
        entries = [
            {"outcome": "OK"},
            {"outcome": "BAD"},
            {"outcome": "OK"},
            {"outcome": "OVR"},
            {"outcome": "PEND"},
        ]
        result = _outcome_counts(entries)
        self.assertEqual(result["OK"], 2)
        self.assertEqual(result["BAD"], 1)
        self.assertEqual(result["OVR"], 1)
        self.assertEqual(result["PEND"], 1)


class TestFindPriorMatch(unittest.TestCase):
    """Passthrough skips re-deliberation, so only outcomes verified in
    reality (CONFIRMED_MARKER) may qualify — an auto-assigned OK measures
    agreement, not outcome."""

    TODAY = date.today().isoformat()

    def _entry(self, outcome="OK", note=""):
        return {
            "date": self.TODAY,
            "context": "refactor aggregator scoring formula",
            "chosen": "extend_trigger",
            "outcome": outcome,
            "note": note,
        }

    def test_confirmed_ok_matches(self):
        entries = [self._entry(note=f"verified {CONFIRMED_MARKER}")]
        match = _find_prior_match("aggregator scoring", entries)
        self.assertEqual(match["chosen"], "extend_trigger")

    def test_unconfirmed_ok_does_not_match(self):
        entries = [self._entry(note="worked as expected")]
        self.assertIsNone(_find_prior_match("aggregator scoring", entries))

    def test_unconfirmed_ok_does_not_shadow_older_confirmed_ok(self):
        older = self._entry(note=f"verified {CONFIRMED_MARKER}")
        newer = self._entry(note="auto")
        newer["chosen"] = "auto_pick"
        match = _find_prior_match("aggregator scoring", [older, newer])
        self.assertEqual(match["chosen"], "extend_trigger")

    def test_confirmed_bad_does_not_match(self):
        entries = [self._entry(outcome="BAD", note=CONFIRMED_MARKER)]
        self.assertIsNone(_find_prior_match("aggregator scoring", entries))


class TestIsConfirmed(unittest.TestCase):
    def test_confirmed_marker_present(self):
        self.assertTrue(_is_confirmed({"note": f"text {CONFIRMED_MARKER} more"}))

    def test_confirmed_marker_absent(self):
        self.assertFalse(_is_confirmed({"note": "no marker here"}))

    def test_empty_note(self):
        self.assertFalse(_is_confirmed({"note": ""}))

    def test_missing_note_field(self):
        self.assertFalse(_is_confirmed({}))


class TestRates(unittest.TestCase):
    def test_empty_entries(self):
        result = _rates([])
        self.assertIsNone(result["bad_rate"])
        self.assertEqual(result["rated_count"], 0)

    def test_only_pending_entries(self):
        entries = [{"outcome": "PEND", "note": ""}, {"outcome": "PEND", "note": ""}]
        result = _rates(entries)
        self.assertIsNone(result["bad_rate"])
        self.assertEqual(result["rated_count"], 0)

    def test_bad_rate(self):
        entries = [
            {"outcome": "OK", "note": CONFIRMED_MARKER},
            {"outcome": "BAD", "note": CONFIRMED_MARKER},
            {"outcome": "BAD", "note": CONFIRMED_MARKER},
        ]
        result = _rates(entries)
        self.assertAlmostEqual(result["bad_rate"], 2.0 / 3.0)

    def test_confirmed_count(self):
        entries = [
            {"outcome": "OK", "note": f"yes {CONFIRMED_MARKER}"},
            {"outcome": "OK", "note": "normal"},
            {"outcome": "BAD", "note": f"also {CONFIRMED_MARKER}"},
        ]
        result = _rates(entries)
        self.assertEqual(result["confirmed_count"], 2)

    def test_unconfirmed_rows_excluded_from_rates(self):
        # Self-assigned OK rows (no marker) must not dilute the rates.
        entries = [
            {"outcome": "OK", "note": "auto"},
            {"outcome": "OK", "note": "auto"},
            {"outcome": "BAD", "note": f"broke prod {CONFIRMED_MARKER}"},
        ]
        result = _rates(entries)
        self.assertEqual(result["rated_count"], 1)
        self.assertEqual(result["rated_count"], result["confirmed_count"])
        self.assertEqual(result["unconfirmed_count"], 2)
        self.assertAlmostEqual(result["bad_rate"], 1.0)


class TestTopKeywords(unittest.TestCase):
    def test_empty_entries(self):
        self.assertEqual(_top_keywords([], k=5), [])

    def test_single_keyword(self):
        result = _top_keywords([{"note": "testing"}], k=5)
        self.assertIn("testing", result)

    def test_stopword_filtering(self):
        result = _top_keywords([{"note": "the and for quality"}], k=5)
        self.assertNotIn("the", result)
        self.assertNotIn("and", result)
        self.assertNotIn("for", result)
        self.assertIn("quality", result)

    def test_top_k_limit(self):
        # delta x5, charlie x4, bravo x3, alpha x2
        notes = "delta delta delta delta delta charlie charlie charlie charlie bravo bravo bravo alpha alpha"
        result = _top_keywords([{"note": notes}], k=3)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], "delta")


class TestFindStalePendings(unittest.TestCase):
    def test_no_pendings(self):
        entries = [
            {"outcome": "OK", "date": "2026-01-01", "context": "x", "chosen": "y"},
        ]
        self.assertEqual(find_stale_pendings(entries), [])

    def test_recent_pending_not_stale(self):
        today = date.today().isoformat()
        entries = [{"outcome": "PEND", "date": today, "context": "recent", "chosen": "x"}]
        self.assertEqual(find_stale_pendings(entries, days_old=STALE_PEND_DAYS), [])

    def test_old_pending_is_stale(self):
        old_date = (date.today() - timedelta(days=10)).isoformat()
        entries = [{"outcome": "PEND", "date": old_date, "context": "old", "chosen": "y"}]
        result = find_stale_pendings(entries, days_old=STALE_PEND_DAYS)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["date"], old_date)

    def test_missing_date_ignored(self):
        entries = [{"outcome": "PEND", "context": "no date", "chosen": "x"}]
        self.assertEqual(find_stale_pendings(entries), [])


class TestFindMissingFeedbackRuns(unittest.TestCase):
    def test_nonexistent_runs_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = find_missing_feedback_runs(Path(td) / "nonexistent", [])
            self.assertEqual(result, [])

    def test_no_runs(self):
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()
            self.assertEqual(find_missing_feedback_runs(runs_dir, []), [])

    def test_missing_feedback_reported(self):
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()
            run_file = runs_dir / "2026-01-15-orphan.json"
            run_file.write_text(
                json.dumps({"chosen_approach": "orphan_approach", "deliberation_log": []}),
                encoding="utf-8",
            )
            result = find_missing_feedback_runs(runs_dir, [], cap=5)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["run"], "2026-01-15-orphan.json")

    def test_missing_feedback_capped(self):
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()
            for i in range(10):
                f = runs_dir / f"2026-01-{15+i:02d}-orphan-{i}.json"
                f.write_text(
                    json.dumps({"chosen_approach": f"orphan_{i}", "deliberation_log": []}),
                    encoding="utf-8",
                )
            result = find_missing_feedback_runs(runs_dir, [], cap=3)
            self.assertEqual(len(result), 3)

    def test_non_canonical_run_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()
            f = runs_dir / "2026-01-15-sub.json"
            f.write_text(json.dumps({"personality": "foo", "chose": "bar"}), encoding="utf-8")
            result = find_missing_feedback_runs(runs_dir, [], cap=5)
            self.assertEqual(result, [])


class TestParseRunsBOM(unittest.TestCase):
    def test_reads_bom_prefixed_run(self):
        # B4: a BOM-prefixed run (PS 5.1 pipe) must parse, not be silently dropped.
        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()
            f = runs_dir / "2026-01-15-bom.json"
            # Write raw UTF-8 bytes with a leading BOM.
            f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"chosen_approach": "x"}).encode("utf-8"))
            runs = parse_runs(runs_dir)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["chosen_approach"], "x")


if __name__ == "__main__":
    unittest.main(verbosity=2)
