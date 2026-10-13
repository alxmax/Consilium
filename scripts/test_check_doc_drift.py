"""Regression tests for check_doc_drift.py's 2026-07-06 self-audit invariants:
_ci_checks_completeness_failures (CI_CHECKS <-> ci.yml),
check_trias_personality_name_parity (Trias team names vs personalities.py), and
check_implement_pipeline_spec_alignment (subagents/cost vs GATE_ITEMS).

Scope: these new invariants only -- check_doc_drift.py's other checks are
exercised by running the real gate in CI, per its own docstring.

Run: python scripts/test_check_doc_drift.py
"""
# tested-by: CONSILIUM-CHECK-DOC-DRIFT-001
# tested-by: CONSILIUM-CHECK-DOC-DRIFT-EXPLAINER-001
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

import check_doc_drift as cdd

REPO_ROOT = Path(__file__).resolve().parent.parent

EXTRAS_CARD = (
    "    {\n"
    "      name: 'Widget gate',\n"
    "      cmd: 'widget_check.py',\n"
    "      desc: 'Checks widgets.',\n"
    "    },\n"
)


def _ci(steps_yaml: str) -> str:
    """Wrap a raw steps block in a minimal but shape-correct ci.yml."""
    return (
        "name: CI\n"
        "jobs:\n"
        "  green-gate:\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-python@v5\n"
        f"{steps_yaml}"
    )


def _extras(cards_body: str) -> str:
    return "function GreenGateSection() {\n  const CI_CHECKS = [\n" + cards_body + "  ];\n"


class CiChecksCompleteness(unittest.TestCase):
    def test_real_repo_files_pass_clean(self):
        ci = cdd._read(".github/workflows/ci.yml")
        extras = cdd._read("docs/architecture/src/extras.jsx")
        self.assertEqual(cdd._ci_checks_completeness_failures(ci, extras), [])

    def test_matching_step_and_card_passes(self):
        ci = _ci(
            "      - name: Widget gate\n"
            "        run: python scripts/widget_check.py\n"
        )
        self.assertEqual(cdd._ci_checks_completeness_failures(ci, _extras(EXTRAS_CARD)), [])

    def test_new_unlisted_script_step_fails(self):
        ci = _ci(
            "      - name: Widget gate\n"
            "        run: python scripts/widget_check.py\n"
            "      - name: Totally new gate\n"
            "        run: python scripts/brand_new_gate.py\n"
        )
        fails = cdd._ci_checks_completeness_failures(ci, _extras(EXTRAS_CARD))
        self.assertEqual(len(fails), 1)
        self.assertIn("brand_new_gate.py", fails[0])
        self.assertIn("Totally new gate", fails[0])

    def test_test_star_steps_are_skipped(self):
        ci = _ci(
            "      - name: Widget unit tests\n"
            "        run: python scripts/test_widget_check.py\n"
        )
        self.assertEqual(cdd._ci_checks_completeness_failures(ci, _extras(EXTRAS_CARD)), [])

    def test_two_steps_sharing_one_script_resolve_to_one_card(self):
        # Two steps sharing one script under different flags resolve to one card --
        # the Skeptic's finding: matching must be by script basename, not full run-line.
        ci = _ci(
            "      - name: Widget gate strict\n"
            "        run: python -X utf8 scripts/widget_check.py gate --strict\n"
            "      - name: Widget freshness\n"
            "        run: python -X utf8 scripts/widget_check.py map --check\n"
        )
        self.assertEqual(cdd._ci_checks_completeness_failures(ci, _extras(EXTRAS_CARD)), [])

    def test_script_less_step_without_allowlist_fails(self):
        ci = _ci(
            "      - name: Some inline bash check\n"
            "        run: |\n"
            "          echo hi\n"
        )
        fails = cdd._ci_checks_completeness_failures(ci, _extras(EXTRAS_CARD))
        self.assertEqual(len(fails), 1)
        self.assertIn("Some inline bash check", fails[0])
        self.assertIn("no ALLOWED_OUT_OF_SCOPE_CI_STEPS entry", fails[0])

    def test_allowlisted_script_less_step_passes(self):
        ci = _ci(
            "      - name: Version bump has a matching CHANGELOG entry\n"
            "        run: |\n"
            "          echo hi\n"
        )
        self.assertEqual(cdd._ci_checks_completeness_failures(ci, _extras(EXTRAS_CARD)), [])

    def test_reverted_card_fails_against_real_ci_yml(self):
        ci = cdd._read(".github/workflows/ci.yml")
        extras = cdd._read("docs/architecture/src/extras.jsx")
        stripped = extras.replace(
            "'Manifest & changelog gate'", "'Manifest & changelog gate REMOVED'"
        ).replace("check_versions.py", "")
        fails = cdd._ci_checks_completeness_failures(ci, stripped)
        self.assertTrue(any("check_versions.py" in f for f in fails))

    def test_missing_ci_checks_array_reports_error(self):
        self.assertEqual(
            cdd._ci_checks_completeness_failures(_ci(""), "no array here"),
            ["[ci_checks_completeness] docs/architecture/src/extras.jsx: CI_CHECKS array not found"],
        )

    def test_uses_only_steps_are_dropped_not_allowlisted(self):
        # actions/checkout and actions/setup-python have no `name:` field -- the parser
        # drops them by construction; they must not need an ALLOWED_OUT_OF_SCOPE entry.
        steps = cdd._parse_ci_named_steps(_ci(""))
        self.assertEqual(steps, [])


class TriasPersonalityNameParity(unittest.TestCase):
    def test_real_repo_files_pass_clean(self):
        self.assertEqual(cdd.check_trias_personality_name_parity(), [])

    def test_extract_personality_names_matches_ssot(self):
        self.assertEqual(
            cdd._extract_personality_names(), {"essentialist", "verifier", "sentinel"}
        )

    def test_extract_jsx_array_names(self):
        jsx = (
            "const LENSES = [\n"
            "  { name: 'Foo', g: 0.5 },\n"
            "  { name: 'Bar', g: 0.5 },\n"
            "];\n"
            "const OTHER = [{ name: 'Unrelated' }];\n"
        )
        self.assertEqual(cdd._extract_jsx_array_names(jsx, "const LENSES = ["), {"foo", "bar"})

    def test_extract_jsx_array_names_missing_marker_returns_empty(self):
        self.assertEqual(cdd._extract_jsx_array_names("no array here", "const LENSES = ["), set())

    def test_trias_jsx_drift_detected(self):
        real = cdd._read("docs/architecture/src/trias.jsx")
        stale = real.replace("name: 'Essentialist'", "name: 'Pioneer'")
        orig = cdd._read
        cdd._read = lambda rel: stale if rel == "docs/architecture/src/trias.jsx" else orig(rel)
        try:
            fails = cdd.check_trias_personality_name_parity()
        finally:
            cdd._read = orig
        self.assertTrue(any("trias.jsx" in f and "pioneer" in f for f in fails))

    def test_modes_jsx_drift_detected(self):
        real = cdd._read("docs/architecture/src/modes.jsx")
        stale = real.replace("name: 'Sentinel'", "name: 'Steward'")
        orig = cdd._read
        cdd._read = lambda rel: stale if rel == "docs/architecture/src/modes.jsx" else orig(rel)
        try:
            fails = cdd.check_trias_personality_name_parity()
        finally:
            cdd._read = orig
        self.assertTrue(any("modes.jsx" in f and "steward" in f for f in fails))

    def test_poster_drift_detected(self):
        real = cdd._read("scripts/make_full_architecture.py")
        stale = real.replace('"Verifier\\n(Sequential)"', '"Architect\\n(Sequential)"')
        orig = cdd._read
        cdd._read = lambda rel: stale if rel == "scripts/make_full_architecture.py" else orig(rel)
        try:
            fails = cdd.check_trias_personality_name_parity()
        finally:
            cdd._read = orig
        self.assertTrue(any("make_full_architecture.py" in f and "architect" in f for f in fails))


class ImplementPipelineSpecAlignment(unittest.TestCase):
    def test_real_repo_files_pass_clean(self):
        self.assertEqual(cdd.check_implement_pipeline_spec_alignment(), [])

    def test_missing_subagent_count_detected(self):
        real = cdd._read("docs/architecture/src/extras.jsx")
        stale = real.replace("3 sub-agents · ~1.1× tokens", "n/a")
        orig = cdd._read
        cdd._read = lambda rel: stale if rel == "docs/architecture/src/extras.jsx" else orig(rel)
        try:
            fails = cdd.check_implement_pipeline_spec_alignment()
        finally:
            cdd._read = orig
        self.assertEqual(len(fails), 2)
        self.assertTrue(any("3 sub-agent" in f for f in fails))
        self.assertTrue(any("1.1" in f for f in fails))

    def test_missing_frontmatter_field_exits_2(self):
        real = cdd._read("modes/implement_pipeline.md")
        stale = real.replace("subagents: 3\n", "")
        orig = cdd._read
        cdd._read = lambda rel: stale if rel == "modes/implement_pipeline.md" else orig(rel)
        try:
            with self.assertRaises(SystemExit) as ctx:
                cdd.check_implement_pipeline_spec_alignment()
            self.assertEqual(ctx.exception.code, 2)
        finally:
            cdd._read = orig


class ReferencedContractsExist(unittest.TestCase):
    def test_real_repo_files_pass_clean(self):
        self.assertEqual(cdd.check_referenced_contracts_exist(), [])

    def test_stale_lens_name_detected(self):
        real = cdd._read("SKILL.md")
        stale = real.replace("`essentialist_lens.md`", "`pioneer_lens.md`")
        self.assertNotEqual(stale, real)
        orig = cdd._read
        cdd._read = lambda rel: stale if rel == "consilium/SKILL.md" else orig(rel)
        try:
            fails = cdd.check_referenced_contracts_exist()
            self.assertTrue(any("prompts/voices/pioneer_lens.md" in f for f in fails))
        finally:
            cdd._read = orig

    def test_missing_mode_path_detected(self):
        real = cdd._read("SKILL.md")
        stale = real + "\nSee `modes/parallel.md`.\n"
        orig = cdd._read
        cdd._read = lambda rel: stale if rel == "consilium/SKILL.md" else orig(rel)
        try:
            fails = cdd.check_referenced_contracts_exist()
            self.assertTrue(any("modes/parallel.md" in f for f in fails))
        finally:
            cdd._read = orig


class SkillMdSize(unittest.TestCase):
    def test_real_skill_md_under_ceiling(self):
        self.assertEqual(cdd.check_skill_md_size(), [])

    def test_oversized_skill_md_detected(self):
        orig = cdd._read
        cdd._read = lambda rel: "x" * (cdd.SKILL_MD_MAX_BYTES + 1) if rel == "SKILL.md" else orig(rel)
        try:
            fails = cdd.check_skill_md_size()
        finally:
            cdd._read = orig
        self.assertEqual(len(fails), 1)
        self.assertIn("skill_md_size", fails[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
