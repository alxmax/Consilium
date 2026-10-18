"""Tests for log_feedback.py pure functions.

Covers fingerprinting, string cleaning/truncation, note derivation,
and entry assembly — the deterministic surface of the feedback logger.

Run:
    python scripts/test_log_feedback.py
    python -m pytest scripts/test_log_feedback.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-LOG-FEEDBACK-001
import json
import subprocess
import sys
import tempfile
import time
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

_SCRIPTS = Path(__file__).resolve().parent.parent / "consilium" / "scripts"
_LOG_CLI = _SCRIPTS / "log_feedback.py"

_LOCK_HOLDER = """import pathlib, sys, time
sys.path.insert(0, sys.argv[1])
from utils import feedback_lock
flag = pathlib.Path(sys.argv[3])
with feedback_lock(sys.argv[2]):
    flag.write_text("held")
    for _ in range(300):
        if pathlib.Path(str(flag) + ".release").exists():
            break
        time.sleep(0.05)
"""


def _report(i: int, **extra) -> dict:
    return {
        "success_criterion": f"concurrent task {i}",
        "chosen_approach": f"opt_{i}",
        "deliberation_log": [],
        **extra,
    }


class TestFeedbackTransaction(unittest.TestCase):
    """The FEEDBACK.html + sidecar read-modify-write is one transaction."""

    def test_lock_excludes_another_process(self):
        import utils
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            fb = Path(td) / "FEEDBACK.html"
            flag = Path(td) / "held"
            holder = subprocess.Popen(
                [sys.executable, "-c", _LOCK_HOLDER, str(_SCRIPTS), str(fb), str(flag)]
            )
            try:
                for _ in range(100):
                    if flag.exists():
                        break
                    time.sleep(0.05)
                self.assertTrue(flag.exists(), "holder never acquired the lock")
                with self.assertRaises(TimeoutError):
                    with utils.feedback_lock(fb, timeout=0.3):
                        pass
            finally:
                Path(str(flag) + ".release").write_text("x")
                holder.wait(timeout=20)
            with utils.feedback_lock(fb, timeout=5):
                pass  # free again once the holder exits

    def test_concurrent_appends_and_outcome_update_all_survive(self):
        from feedback import parse_feedback
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            fb = Path(td) / "FEEDBACK.html"
            seed = "runs/2026-10-18_seed.json"
            seed_rep = _report(0)

            def cli(report, *args):
                proc = subprocess.Popen(
                    [sys.executable, str(_LOG_CLI), "--feedback", str(fb), *args],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True,
                )
                assert proc.stdin is not None
                proc.stdin.write(json.dumps(report))
                proc.stdin.close()
                return proc

            cli(seed_rep, "--run-path", seed).wait(timeout=60)
            procs = [cli(_report(i)) for i in range(1, 9)]
            procs.append(cli(seed_rep, "--run-path", seed, "--outcome", "BAD"))
            for p in procs:
                p.wait(timeout=120)
            rows = parse_feedback(fb)
            self.assertEqual(sorted(r["chosen"] for r in rows),
                             sorted(["opt_0"] + [f"opt_{i}" for i in range(1, 9)]))
            by_chosen = {r["chosen"]: r for r in rows}
            self.assertEqual(by_chosen["opt_0"]["outcome"], "BAD")

    def test_row_is_written_before_the_sidecar(self):
        import log_feedback as lf
        from feedback import parse_feedback
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            fb = Path(td) / "FEEDBACK.html"
            run = "runs/2026-10-18_a.json"
            entry = build_entry(_report(1))
            seen = {}
            real = lf._save_map

            def failing_save(runs_dir, run_map):
                seen["row_present"] = any(
                    r["chosen"] == "opt_1" for r in parse_feedback(fb)
                )
                raise OSError("disk full")

            lf._save_map = failing_save
            try:
                with self.assertRaises(OSError):
                    lf.append_entry(fb, entry, run)
            finally:
                lf._save_map = real
            self.assertTrue(seen.get("row_present"),
                            "sidecar was saved before the row was written")
            # retry after the interruption: no duplicate row, sidecar healed
            lf.append_entry(fb, entry, run)
            self.assertEqual(len(parse_feedback(fb)), 1)
            self.assertIn(run, lf._load_map(fb.parent / "runs").values())


class TestWeakFlag(unittest.TestCase):
    """WEAK is advisory quality metadata for a below-floor run, not an
    observed outcome: the row stays PEND and carries a [weak] marker."""

    def test_build_entry_marks_weak_and_keeps_pend(self):
        entry = build_entry(_report(1), weak=True)
        self.assertEqual(entry["outcome"], "PEND")
        self.assertIn("[weak]", entry["note"])
        self.assertNotIn("[weak]", build_entry(_report(1))["note"])

    def test_below_floor_run_round_trips_through_the_logger(self):
        from confidence import check_mode_floor
        from feedback import parse_feedback
        floor = check_mode_floor("sequential", 0.65)
        self.assertTrue(floor["below_floor"])
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            fb = Path(td) / "FEEDBACK.html"
            proc = subprocess.run(
                [sys.executable, str(_LOG_CLI), "--feedback", str(fb), "--weak"],
                input=json.dumps(_report(1)), capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            rows = parse_feedback(fb)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["outcome"], "PEND")
            self.assertIn("[weak]", rows[0]["note"])

    def test_weak_is_not_an_outcome_value(self):
        proc = subprocess.run(
            [sys.executable, str(_LOG_CLI), "--outcome", "WEAK", "--dry-run"],
            input=json.dumps(_report(1)), capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
