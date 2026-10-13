"""Tests for the pre-dispatch irreversibility consent gate (scope_gate.consent_required).

Generator now runs FIRST in Sequential, so the irreversibility consent gate moved
ahead of every voice (SKILL.md Step 1.6). scope_gate.decide() carries the path-based
signal. The review's blocking condition (2026-06-13, Reviewer 6) requires that the gate:
  (a) fires on a sensitive/irreversible path BEFORE any voice runs, and
  (b) FAILS SAFE — an undeterminable change must NOT silently bypass consent
      (Reviewer 3: must not inherit should_skip's fail-OPEN default).

These are pure-function tests over decide(); the live "Generator output absent at
consent-fire" assertion is an orchestrator contract documented in SKILL.md Step 1.6
that this signal underpins.

Run:
    python scripts/test_consent_gate.py
    python -m pytest scripts/test_consent_gate.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-SCOPE-GATE-001
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from scope_gate import DEFAULT_CONFIG, decide  # noqa: E402


def _summary(files=1, added=4, removed=0):
    return {"files_changed": files, "lines_added": added, "lines_removed": removed}


class TestConsentGate(unittest.TestCase):
    def test_sensitive_path_requires_consent(self):
        # A blocklist (irreversible/sensitive) path must trigger pre-dispatch consent.
        out = decide(_summary(files=1), ["migrations/0007_drop_users.py"], DEFAULT_CONFIG)
        self.assertTrue(out["consent_required"])
        self.assertEqual(out["magnitude"], "critical")
        # And it must not be skippable — consent precedes deliberation.
        self.assertFalse(out["should_skip"])

    def test_auth_path_requires_consent(self):
        out = decide(_summary(files=1), ["auth/session.py"], DEFAULT_CONFIG)
        self.assertTrue(out["consent_required"])

    def test_ordinary_change_no_consent(self):
        # A small ordinary change does not require consent (and may even skip).
        out = decide(_summary(files=1, added=4), ["docs/notes.md"], DEFAULT_CONFIG)
        self.assertFalse(out["consent_required"])

    def test_large_ordinary_change_no_consent(self):
        # Large but non-sensitive: deliberate, but no irreversibility consent.
        out = decide(_summary(files=8, added=400), ["src/a.py", "src/b.py"], DEFAULT_CONFIG)
        self.assertFalse(out["consent_required"])
        self.assertFalse(out["should_skip"])

    def test_no_changes_no_consent(self):
        out = decide(_summary(files=0, added=0), [], DEFAULT_CONFIG)
        self.assertFalse(out["consent_required"])

    def test_probe_error_fails_safe_to_consent(self):
        # Reviewer 3's catch: an undeterminable change must FAIL SAFE — require
        # consent, never silently bypass it (unlike should_skip's fail-OPEN).
        out = decide({"error": "not a git repository"}, [], DEFAULT_CONFIG)
        self.assertTrue(out["consent_required"])
        self.assertFalse(out["should_skip"])

    def test_consent_required_always_present(self):
        # The field is part of the contract on every return path.
        for summary, paths in (
            (_summary(files=0), []),
            (_summary(files=1), ["docs/x.md"]),
            (_summary(files=1), [".github/workflows/ci.yml"]),
            ({"error": "bad ref"}, []),
        ):
            out = decide(summary, paths, DEFAULT_CONFIG)
            self.assertIn("consent_required", out)
            self.assertIsInstance(out["consent_required"], bool)


if __name__ == "__main__":
    unittest.main()
