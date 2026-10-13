"""Tests for strip_context.py pure JSON projection functions.

Covers strip_for_control (drops rationale), strip_for_conservator
(filters to valid verdicts), and strip_for_trias (token-budget truncation).

Run:
    python scripts/test_strip_context.py
    python -m pytest scripts/test_strip_context.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-STRIP-CONTEXT-001
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from strip_context import strip_for_control, strip_for_conservator, strip_for_trias


class TestStripForControl(unittest.TestCase):
    def test_keeps_only_id_summary_sketch(self):
        data = {
            "candidates": [
                {
                    "id": "A",
                    "summary": "test",
                    "sketch": "code",
                    "rationale": "should be dropped",
                    "extra": "also dropped",
                }
            ]
        }
        result = strip_for_control(data)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertNotIn("rationale", result["candidates"][0])
        self.assertNotIn("extra", result["candidates"][0])
        self.assertEqual(result["candidates"][0]["id"], "A")

    def test_empty_candidates(self):
        self.assertEqual(strip_for_control({"candidates": []})["candidates"], [])

    def test_missing_candidates_key(self):
        self.assertEqual(strip_for_control({})["candidates"], [])

    def test_skips_non_dict_candidates(self):
        data = {"candidates": [{"id": "A", "summary": "ok", "sketch": "x"}, "invalid", None]}
        result = strip_for_control(data)
        self.assertEqual(len(result["candidates"]), 1)

    def test_missing_optional_fields_ok(self):
        data = {"candidates": [{"id": "A"}]}
        result = strip_for_control(data)
        self.assertEqual(result["candidates"], [{"id": "A"}])


class TestStripForConservator(unittest.TestCase):
    def test_keeps_only_valid_verdicts(self):
        data = {
            "candidates": [
                {"id": "A", "summary": "ok", "sketch": "code"},
                {"id": "B", "summary": "bad", "sketch": "code"},
            ],
            "verdicts": [
                {"id": "A", "valid": True, "issues": "dropped"},
                {"id": "B", "valid": False, "issues": "dropped"},
            ],
        }
        result = strip_for_conservator(data)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["id"], "A")
        self.assertNotIn("issues", result["candidates"][0])

    def test_drops_non_dict_verdict(self):
        data = {
            "candidates": [{"id": "A", "summary": "t", "sketch": "x"}],
            "verdicts": [{"id": "A"}],  # missing valid key
        }
        result = strip_for_conservator(data)
        self.assertEqual(result["candidates"], [])

    def test_verdict_candidate_mismatch_skipped(self):
        data = {
            "candidates": [{"id": "A", "summary": "t", "sketch": "x"}],
            "verdicts": [{"id": "B", "valid": True}],
        }
        result = strip_for_conservator(data)
        self.assertEqual(result["candidates"], [])

    def test_empty_inputs(self):
        self.assertEqual(strip_for_conservator({})["candidates"], [])

    def test_output_fields_limited(self):
        data = {
            "candidates": [{"id": "C", "summary": "fix", "sketch": "delta", "author": "bob"}],
            "verdicts": [{"id": "C", "valid": True, "notes": "dropped"}],
        }
        result = strip_for_conservator(data)
        self.assertEqual(result["candidates"][0], {"id": "C", "summary": "fix", "sketch": "delta"})


class TestStripForTrias(unittest.TestCase):
    def test_short_text_unchanged(self):
        text = "short text"
        self.assertEqual(strip_for_trias(text, max_tokens=1000), text)

    def test_long_text_truncated(self):
        text = "x" * 500
        result = strip_for_trias(text, max_tokens=10)
        self.assertIn("[... context truncated", result)
        self.assertIn("10", result)

    def test_truncated_text_shorter_than_original(self):
        text = "x" * 500
        result = strip_for_trias(text, max_tokens=10)
        self.assertLess(len(result), len(text))

    def test_empty_text_unchanged(self):
        self.assertEqual(strip_for_trias("", max_tokens=100), "")

    def test_exactly_at_limit_not_truncated(self):
        text = "a" * 40  # 40 chars = 10 tokens * 4 chars/token
        result = strip_for_trias(text, max_tokens=10)
        self.assertEqual(result, text)


class BomInputTest(unittest.TestCase):
    # PS 5.1 pipes/redirects prepend a UTF-8 BOM. main() must strip it (exit 0
    # on valid JSON) and exit 2 with one stderr line on malformed input - never
    # a raw JSONDecodeError traceback (audit 2026-07-02).

    BOM = bytes([0xEF, 0xBB, 0xBF])

    def _run_main(self, argv):
        import contextlib
        import io
        from strip_context import main as sc_main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = sc_main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_bom_valid_json_parses(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "in.json"
            p.write_bytes(self.BOM + json.dumps({"candidates": []}).encode())
            rc, out, _ = self._run_main(["--for", "control", "--input", str(p)])
        self.assertEqual(rc, 0)
        self.assertIn("candidates", out)

    def test_bom_malformed_json_clean_exit(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_bytes(self.BOM + b"not json")
            rc, _, err = self._run_main(["--for", "control", "--input", str(p)])
        self.assertEqual(rc, 2)
        self.assertIn("invalid JSON", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
