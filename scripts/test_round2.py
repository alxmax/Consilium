"""Tests for ROUND2 architecture additions.

Run:
    python scripts/test_round2.py
    python -m pytest scripts/test_round2.py -v  (if pytest available)
"""
# tested-by: CONSILIUM-AGGREGATOR-001
# tested-by: CONSILIUM-VALIDATE-REPORT-001
# tested-by: CONSILIUM-VOCABULARY-MAP-001
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path

from vocabulary_map import translate, compute_tokens_budget, VOCABULARY_MAP
import aggregator
import validate_report


class TestVocabularyMap(unittest.TestCase):
    def test_translate_reversibility_complete(self):
        result = translate("reversibility", "complete")
        self.assertIn("ușor", result)

    def test_translate_magnitude_critical(self):
        result = translate("magnitude", "critical")
        self.assertIn("major", result.lower())

    def test_translate_meta_recommendation_scale_down(self):
        result = translate("meta_recommendation", "scale_down")
        self.assertTrue(len(result) > 0)

    def test_translate_unknown_category(self):
        result = translate("nonexistent", "value")
        self.assertEqual(result, "value")

    def test_translate_none_value(self):
        result = translate("meta_recommendation", None)
        self.assertEqual(result, "")

    def test_compute_tokens_budget_trivial_complete(self):
        budget = compute_tokens_budget("trivial", "complete")
        self.assertEqual(budget["generator"], 300)
        self.assertEqual(budget["control"], 300)

    def test_compute_tokens_budget_critical_irreversible(self):
        budget = compute_tokens_budget("critical", "irreversible")
        self.assertEqual(budget["generator"], 4000)

    def test_compute_tokens_budget_scale_down_override(self):
        budget = compute_tokens_budget("critical", "irreversible", meta="scale_down")
        self.assertEqual(budget["generator"], 300)

    def test_compute_tokens_budget_unknown_combo_defaults(self):
        budget = compute_tokens_budget("trivial", "irreversible")
        self.assertEqual(budget["generator"], 800)

    def test_compute_tokens_budget_scale_up_critical_clamped(self):
        # critical+irreversible base=4000; +50% would be 6000 but clamped to 4000 (cap is intentional)
        budget = compute_tokens_budget("critical", "irreversible", meta="scale_up")
        self.assertEqual(budget["generator"], 4000)
        self.assertEqual(budget["control"], 4000)

    def test_compute_tokens_budget_scale_up_moderate_increases(self):
        # moderate+partial base=800; +50% rounded to nearest 100 = 1200
        budget = compute_tokens_budget("moderate", "partial", meta="scale_up")
        self.assertEqual(budget["generator"], 1200)


class TestVocabularyMapCases(unittest.TestCase):
    # verifies: CONSILIUM-VOCABULARY-MAP-001#CASE-1
    def test_translate_reversibility_complete_exact(self):
        self.assertEqual(
            translate("reversibility", "complete"), "ușor de anulat")

    # verifies: CONSILIUM-VOCABULARY-MAP-001#CASE-2
    def test_translate_verdict_go(self):
        self.assertEqual(translate("verdict", "GO"), "aprobat de majoritate")

    # verifies: CONSILIUM-VOCABULARY-MAP-001#CASE-3
    def test_compute_tokens_budget_critical_irreversible_dict(self):
        self.assertEqual(
            compute_tokens_budget("critical", "irreversible"),
            {"generator": 4000, "control": 4000},
        )

    # verifies: CONSILIUM-VOCABULARY-MAP-001#CASE-4
    def test_scale_down_is_300_for_every_magnitude_and_reversibility(self):
        for magnitude in ("trivial", "moderate", "high", "critical"):
            for reversibility in ("complete", "partial", "irreversible"):
                self.assertEqual(
                    compute_tokens_budget(
                        magnitude, reversibility, meta="scale_down"),
                    {"generator": 300, "control": 300},
                )

    # verifies: CONSILIUM-VOCABULARY-MAP-001#CASE-5
    def test_translate_unknown_category_or_value_returns_str_value(self):
        self.assertEqual(translate("nonexistent", "value"), "value")
        self.assertEqual(translate("reversibility", "bogus"), "bogus")


class TestAggregateRound2(unittest.TestCase):
    def _base_conservator(self, reversibility="complete", magnitude="trivial", meta=None, flag=False):
        # Mirror the real conservator.md output contract: every per-candidate
        # field (regression_risk, meta_recommendation, irreversibility_flag)
        # lives inside scores[i]. The voice emits NO top-level regression_risk
        # or irreversibility_flag — aggregate_sequential reads them from scores[].
        # (Earlier this fixture injected top-level copies that masked the nesting
        # bug — TODO bug-audit 2026-05-31, Cluster A.)
        return {
            "scores": [
                {
                    "id": "A",
                    "regression_risk": {
                        "reversibility": reversibility,
                        "magnitude": magnitude,
                        "net_concern": 0.05,
                    },
                    "meta_recommendation": meta,
                    "irreversibility_flag": flag,
                    "tokens_budget": {"generator": 300, "control": 300},
                }
            ],
        }

    def _base_generator(self, preferred: "str | None" = "A", abstain=False):
        return {
            "candidates": [{"id": "A"}, {"id": "do_nothing"}],
            "preferred": preferred,
            "abstain": {"triggered": abstain, "reason": "test" if abstain else None},
            "challenge_upward": {"triggered": False, "reason": None},
        }

    def _base_control(self, glossary_fail=False, disagreements=None):
        return {
            "glossary": {"term": "definition"},
            "glossary_fail": glossary_fail,
            "glossary_attempts": [],
            "disagreements": disagreements or [],
            "verdicts": [{"id": "A", "valid": True, "issues": [], "tests_to_write": []}],
        }

    def test_glossary_fail_blocks(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(),
            self._base_control(glossary_fail=True),
            self._base_conservator(),
        )
        self.assertEqual(result["result"], "BLOCK")
        self.assertEqual(result["reason"], "glossary_fail")

    # verifies: CONSILIUM-AGGREGATOR-001#CASE-4
    def test_glossary_fail_blocks_regardless_of_other_signals(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(abstain=True),
            self._base_control(
                glossary_fail=True,
                disagreements=[
                    {"between": ["g", "c"], "type": "substantial",
                     "detail": "x"}
                ],
            ),
            self._base_conservator(meta="scale_up", flag=True),
        )
        self.assertEqual(result["result"], "BLOCK")
        self.assertEqual(result["reason"], "glossary_fail")

    def test_irreversibility_flag_blocks(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(),
            self._base_control(),
            self._base_conservator(flag=True),
        )
        self.assertEqual(result["result"], "BLOCK")
        self.assertEqual(result["reason"], "irreversibility_no_consent")

    def test_substantial_disagreement_reworks(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(),
            self._base_control(disagreements=[{"between": ["g", "c"], "type": "substantial", "detail": "x"}]),
            self._base_conservator(),
        )
        self.assertEqual(result["result"], "REWORK")

    def test_scale_down_adapts_short(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(),
            self._base_control(),
            self._base_conservator(meta="scale_down"),
        )
        self.assertEqual(result["result"], "ADAPT_SHORT")

    def test_scale_up_adapts_extended(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(),
            self._base_control(),
            self._base_conservator(meta="scale_up"),
        )
        self.assertEqual(result["result"], "ADAPT_EXTENDED")

    # verifies: CONSILIUM-AGGREGATOR-001#CASE-5
    def test_three_triggers_escalate(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(abstain=True),
            self._base_control(
                disagreements=[{"between": ["g", "c"], "type": "substantial", "detail": "x"}]
            ),
            self._base_conservator(meta="scale_up"),
        )
        self.assertEqual(result["result"], "ESCALATE")
        self.assertEqual(len(result["triggers"]), 3)

    def test_normal_aggregate_returns_chosen(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(preferred="A"),
            self._base_control(),
            self._base_conservator(),
        )
        self.assertEqual(result["result"], "AGGREGATE")
        self.assertEqual(result["chosen"], "A")

    def test_preferred_not_in_candidates_raises(self):
        # Guard (2026-06-28 Skeptic): a generator.preferred that names no real
        # candidate must fail loud, not silently become chosen — a non-existent
        # id collapses every confidence_per_option to the 0.5 base with no error.
        with self.assertRaises(ValueError):
            aggregator.aggregate_sequential(
                self._base_generator(preferred="ghost_candidate"),
                self._base_control(),
                self._base_conservator(),
            )

    def test_preferred_none_does_not_raise(self):
        # Boundary: preferred=None is the "no explicit winner" case (chosen=None),
        # not a hallucination — it stays permitted and must not trip the guard.
        result = aggregator.aggregate_sequential(
            self._base_generator(preferred=None),
            self._base_control(),
            self._base_conservator(),
        )
        self.assertEqual(result["result"], "AGGREGATE")
        self.assertIsNone(result["chosen"])

    def test_conservative_override_empty_candidates_raises(self):
        # Guard (audit 2026-07-02): an empty candidates list is an upstream
        # bundle bug — the default scheme used to exit 0 with a false "all
        # candidates vetoed by conservator" reason (nothing was vetoed) while
        # the sibling schemes raise ValueError. It must fail loud like them.
        with self.assertRaises(ValueError):
            aggregator.aggregate_conservative_override([])

    def test_low_methodology_confidence_warns(self):
        result = aggregator.aggregate_sequential(
            self._base_generator(abstain=True),
            self._base_control(disagreements=[
                {"type": "substantial", "detail": "x"},
                {"type": "substantial", "detail": "y"},
                {"type": "substantial", "detail": "z"},
            ]),
            self._base_conservator(),
        )
        # abstain + 3 substantial disagreements = triggers ["substantial_disagreement", "generator_abstain"] → 2 triggers → REWORK
        self.assertIn(result["result"], ("REWORK", "ESCALATE", "AGGREGATE"))


class TestConservativeOverride(unittest.TestCase):
    """Behavioral coverage for the documented default aggregation scheme.

    CONSILIUM-AGGREGATOR-001 declares two acceptance criteria for
    conservative_override (all-vetoed retry, lower-risk-ranks-first) but only
    the sequential routing outcomes were actually tested. These lock the veto
    boundary (SKILL.md: risk>0.8 strict), the safer-wins tie-break (a bug that
    already shipped once — TODO.md:108), and the escalation path.
    """

    @staticmethod
    def _cand(cid, gen, ctrl, cons):
        return {"id": cid, "scores": {"generator": gen, "control": ctrl, "conservator": cons}}

    def test_veto_boundary_is_strict(self):
        # risk == 0.80 survives (not > 0.8); risk == 0.81 is vetoed.
        result = aggregator.aggregate_conservative_override([
            self._cand("at_080", 0.7, 0.7, 0.80),
            self._cand("over_081", 0.9, 0.9, 0.81),
        ])
        self.assertEqual(result["chosen"], "at_080")
        self.assertEqual([v["id"] for v in result["vetoed"]], ["over_081"])

    # verifies: CONSILIUM-AGGREGATOR-001#CASE-1
    def test_all_vetoed_auto_relax_suggests_retry(self):
        # Acceptance #1: every candidate over threshold, auto_relax on ->
        # chosen null + non-empty retry_suggested with the lowest risk relaxed.
        result = aggregator.aggregate_conservative_override([
            self._cand("a", 0.8, 0.8, 0.84),
            self._cand("b", 0.8, 0.8, 0.82),
        ])
        self.assertIsNone(result["chosen"])
        self.assertIn("retry_suggested", result)
        self.assertEqual(result["retry_suggested"]["relaxed_threshold"], 0.82)
        self.assertEqual(result["retry_suggested"]["lowest_risk_candidate"]["id"], "b")
        self.assertNotIn("escalation_required", result)

    # verifies: CONSILIUM-AGGREGATOR-001#CASE-2
    def test_lower_risk_ranks_first(self):
        # Acceptance #2: identical generator+control, different conservator ->
        # the lower-risk candidate ranks first.
        result = aggregator.aggregate_conservative_override([
            self._cand("risky", 0.7, 0.7, 0.55),
            self._cand("safe", 0.7, 0.7, 0.20),
        ])
        self.assertEqual(result["chosen"], "safe")
        self.assertEqual(result["ranking"][0]["id"], "safe")

    def test_equal_score_tiebreak_prefers_safer(self):
        # Genuine weighted-score tie (both == 0.6): safer (lower conservator)
        # must win. Locks the TODO.md:108 "safer wins on tie" fix — the prior
        # bug broke the tie by insertion order instead.
        result = aggregator.aggregate_conservative_override([
            self._cand("hi_risk", 0.7, 0.7, 0.60),   # safety 0.4 -> (0.7+0.7+0.4)/3 = 0.6
            self._cand("lo_risk", 0.6, 0.6, 0.40),   # safety 0.6 -> (0.6+0.6+0.6)/3 = 0.6
        ])
        self.assertAlmostEqual(result["ranking"][0]["score"], result["ranking"][1]["score"])
        self.assertEqual(result["chosen"], "lo_risk")

    def test_all_vetoed_beyond_relaxed_cap_escalates(self):
        # Lowest risk exceeds RELAXED_VETO_CAP (0.85): relaxing would not help,
        # so escalate instead of suggesting a retry.
        result = aggregator.aggregate_conservative_override([
            self._cand("a", 0.8, 0.8, 0.92),
            self._cand("b", 0.8, 0.8, 0.90),
        ])
        self.assertIsNone(result["chosen"])
        self.assertTrue(result["escalation_required"])
        self.assertNotIn("retry_suggested", result)


class TestAdmissibility(unittest.TestCase):
    """A candidate that is invalid, not evaluated by Control, or vetoed by the
    Conservator must not become a normal recommendation — in either the
    sequential cascade or conservative_override (the Step 5 default)."""

    @staticmethod
    def _gen(preferred="A"):
        return {
            "candidates": [{"id": "A"}, {"id": "B"}, {"id": "do_nothing"}],
            "preferred": preferred,
            "abstain": {"triggered": False, "reason": None},
        }

    @staticmethod
    def _ctl(verdicts):
        return {
            "glossary": {"t": "d"}, "glossary_fail": False,
            "glossary_attempts": [], "disagreements": [], "verdicts": verdicts,
        }

    @staticmethod
    def _cons(concerns):
        return {"scores": [
            {"id": cid, "regression_risk": {
                "reversibility": "complete", "magnitude": "trivial",
                "net_concern": nc},
             "meta_recommendation": None, "irreversibility_flag": False}
            for cid, nc in concerns.items()
        ]}

    @staticmethod
    def _ok(cid):
        return {"id": cid, "valid": True, "issues": [], "tests_to_write": []}

    def _seq(self, verdicts, concerns=None, waiver=None):
        return aggregator.aggregate_sequential(
            self._gen(), self._ctl(verdicts),
            self._cons(concerns or {"A": 0.05, "B": 0.1, "do_nothing": 0.05}),
            waiver=waiver,
        )

    # --- sequential cascade -------------------------------------------------
    def test_valid_evaluated_preferred_is_aggregated(self):
        r = self._seq([self._ok("A"), self._ok("B")])
        self.assertEqual(r["result"], "AGGREGATE")
        self.assertEqual(r["chosen"], "A")
        self.assertTrue(r["admissibility"]["checked"])

    def test_invalid_preferred_is_not_chosen(self):
        bad = {"id": "A", "valid": False, "issues": [], "tests_to_write": []}
        r = self._seq([bad, self._ok("B")])
        self.assertEqual(r["result"], "REWORK")
        self.assertIsNone(r["chosen"])
        self.assertEqual(r["reason"], "preferred_inadmissible")
        self.assertIn("invalid", r["inadmissible_reasons"])
        self.assertEqual(r["admissible_alternatives"], ["B"])

    def test_control_absent_is_not_a_normal_recommendation(self):
        for verdicts in ([], [self._ok("B")]):  # no verdicts / none for A
            r = self._seq(verdicts)
            self.assertEqual(r["result"], "REWORK", verdicts)
            self.assertIn("not_evaluated", r["inadmissible_reasons"])

    def test_vetoed_preferred_is_not_chosen(self):
        for concern in (0.81, 0.95, 0.99):
            r = self._seq([self._ok("A"), self._ok("B")],
                          {"A": concern, "B": 0.1, "do_nothing": 0.05})
            self.assertEqual(r["result"], "REWORK", concern)
            self.assertIn("vetoed", r["inadmissible_reasons"])

    def test_veto_boundary_is_strict_in_sequential(self):
        r = self._seq([self._ok("A")], {"A": 0.80})
        self.assertEqual(r["result"], "AGGREGATE")

    def test_explicit_waiver_is_recorded_and_allows_the_pick(self):
        bad = {"id": "A", "valid": False, "issues": [], "tests_to_write": []}
        r = self._seq([bad], waiver={"id": "A", "reason": "user accepted the risk"})
        self.assertEqual(r["result"], "AGGREGATE")
        self.assertEqual(r["chosen"], "A")
        w = r["admissibility"]["waived"]
        self.assertEqual((w["id"], w["reason"]), ("A", "user accepted the risk"))
        self.assertIn("invalid", w["reasons"])

    def test_waiver_without_reason_or_for_another_id_is_ignored(self):
        bad = {"id": "A", "valid": False, "issues": [], "tests_to_write": []}
        for waiver in ({"id": "A", "reason": "  "}, {"id": "B", "reason": "x"},
                       {"id": "A"}, "yes"):
            r = self._seq([bad], waiver=waiver)
            self.assertEqual(r["result"], "REWORK", waiver)

    # --- conservative_override (Step 5 default) -------------------------------
    @staticmethod
    def _cand(cid, gen, ctrl, cons, **extra):
        return {"id": cid, "scores": {
            "generator": gen, "control": ctrl, "conservator": cons}, **extra}

    def test_control_rejected_candidate_cannot_win_on_other_voices(self):
        r = aggregator.aggregate_conservative_override([
            self._cand("invalid_best", 1.0, 0.0, 0.05),
            self._cand("valid_ok", 0.6, 0.6, 0.3),
        ])
        self.assertEqual(r["chosen"], "valid_ok")
        v = {x["id"]: x for x in r["vetoed"]}
        self.assertEqual(v["invalid_best"]["reason"], "control_invalid")

    def test_explicit_valid_false_is_rejected(self):
        r = aggregator.aggregate_conservative_override([
            self._cand("flagged", 1.0, 0.9, 0.05, valid=False),
            self._cand("ok", 0.5, 0.5, 0.3),
        ])
        self.assertEqual(r["chosen"], "ok")

    def test_all_control_rejected_yields_no_choice_and_no_relax_hint(self):
        r = aggregator.aggregate_conservative_override([
            self._cand("a", 0.9, 0.0, 0.1),
            self._cand("b", 0.8, 0.0, 0.2),
        ])
        self.assertIsNone(r["chosen"])
        self.assertNotIn("retry_suggested", r)
        self.assertTrue(r.get("escalation_required"))

    def test_relax_hint_ignores_control_rejected_candidates(self):
        r = aggregator.aggregate_conservative_override([
            self._cand("invalid_low_risk", 0.9, 0.0, 0.05),
            self._cand("valid_high_risk", 0.8, 0.8, 0.84),
        ])
        self.assertIsNone(r["chosen"])
        rs = r["retry_suggested"]
        self.assertEqual(rs["lowest_risk_candidate"]["id"], "valid_high_risk")

    # --- report validation ----------------------------------------------------
    @staticmethod
    def _report(verdicts, concerns, waived=None, chosen="A"):
        agg = {"scheme": "sequential", "result": "AGGREGATE", "chosen": chosen,
               "admissibility": {"checked": True}}
        if waived:
            agg["admissibility"]["waived"] = waived
        return {
            "chosen_approach": chosen, "pipeline_executed": True,
            "deliberation_log": [
                {"step": "generator", "candidates": [{"id": "A"}]},
                {"step": "control", "verdicts": verdicts},
                {"step": "conservator", "scores": [
                    {"id": cid, "regression_risk": {"net_concern": nc}}
                    for cid, nc in concerns.items()]},
                {"step": "aggregate", "scheme": "sequential", "result": agg},
            ],
        }

    def test_validator_accepts_an_admissible_choice(self):
        rep = self._report([self._ok("A")], {"A": 0.1})
        self.assertEqual(validate_report._validate_admissibility(rep), [])

    def test_validator_rejects_invalid_unevaluated_and_vetoed_choices(self):
        bad = {"id": "A", "valid": False, "issues": []}
        for label, rep in (
            ("invalid", self._report([bad], {"A": 0.1})),
            ("not evaluated", self._report([], {"A": 0.1})),
            ("vetoed", self._report([self._ok("A")], {"A": 0.95})),
        ):
            problems = validate_report._validate_admissibility(rep)
            self.assertTrue(any("admissib" in p for p in problems), label)
            self.assertTrue(
                any("admissib" in p for p in validate_report.validate(rep)
                    if "admissib" in p) or problems, label)

    def test_validator_accepts_a_recorded_waiver_only(self):
        bad = {"id": "A", "valid": False, "issues": []}
        waived = {"id": "A", "reasons": ["invalid"], "reason": "user accepted"}
        self.assertEqual(validate_report._validate_admissibility(
            self._report([bad], {"A": 0.1}, waived=waived)), [])
        for w in ({"id": "A", "reasons": ["invalid"], "reason": ""},
                  {"id": "B", "reasons": ["invalid"], "reason": "x"}):
            self.assertTrue(validate_report._validate_admissibility(
                self._report([bad], {"A": 0.1}, waived=w)), w)

    def test_validator_leaves_legacy_reports_without_the_block_readable(self):
        bad = {"id": "A", "valid": False, "issues": []}
        rep = self._report([bad], {"A": 0.95})
        del rep["deliberation_log"][3]["result"]["admissibility"]
        self.assertEqual(validate_report._validate_admissibility(rep), [])

    def test_validator_does_not_apply_the_net_concern_veto_to_other_schemes(self):
        rep = self._report([self._ok("A")], {"A": 0.95})
        rep["deliberation_log"][3]["scheme"] = "conservative_override"
        rep["deliberation_log"][3]["result"]["scheme"] = "conservative_override"
        self.assertEqual(validate_report._validate_admissibility(rep), [])
        bad = {"id": "A", "valid": False, "issues": []}
        rep2 = self._report([bad], {"A": 0.1})
        rep2["deliberation_log"][3]["scheme"] = "conservative_override"
        self.assertTrue(validate_report._validate_admissibility(rep2))

    def test_validator_skips_reports_it_cannot_judge(self):
        self.assertEqual(validate_report._validate_admissibility(
            {"chosen_approach": "skipped", "skipped": True}), [])
        self.assertEqual(validate_report._validate_admissibility(
            {"chosen_approach": None, "pipeline_executed": True,
             "deliberation_log": []}), [])


class TestTeamVote(unittest.TestCase):
    # verifies: CONSILIUM-AGGREGATOR-001#CASE-3
    def test_two_one_vote_picks_majority_and_records_dissent(self):
        result = aggregator.aggregate_team_vote(
            [
                {"name": "essentialist", "chose": "A"},
                {"name": "verifier", "chose": "A"},
                {"name": "sentinel", "chose": "B"},
            ],
            [{"id": "A"}, {"id": "B"}],
        )
        self.assertEqual(result["vote_pattern"], "2-1")
        self.assertEqual(result["chosen"], "A")
        self.assertTrue(result["dissent"])


class TestValidateReportRound2(unittest.TestCase):
    def test_regression_risk_scalar_still_valid(self):
        problems = validate_report._validate_regression_risk(0.5)
        self.assertEqual(problems, [])

    def test_regression_risk_object_valid(self):
        problems = validate_report._validate_regression_risk({
            "reversibility": "complete",
            "magnitude": "trivial",
            "net_concern": 0.05,
        })
        self.assertEqual(problems, [])

    def test_regression_risk_object_missing_magnitude(self):
        problems = validate_report._validate_regression_risk({
            "reversibility": "complete",
            "net_concern": 0.05,
        })
        self.assertTrue(any("magnitude" in p for p in problems))

    def test_regression_risk_invalid_reversibility(self):
        problems = validate_report._validate_regression_risk({
            "reversibility": "unknown",
            "magnitude": "trivial",
        })
        self.assertTrue(any("reversibility" in p for p in problems))

    def test_regression_risk_scalar_out_of_range(self):
        problems = validate_report._validate_regression_risk(1.5)
        self.assertTrue(len(problems) > 0)

    def test_regression_risk_wrong_type(self):
        problems = validate_report._validate_regression_risk("high")
        self.assertTrue(len(problems) > 0)


class TestValidateTriasTrigger(unittest.TestCase):
    """GAP#1: _validate_trias must fire on telemetry.mode == 'trias', not only
    on team == 'trias'. Real trias runs key off mode and frequently omit team;
    gating on team alone silently skipped every trias check on those runs."""

    def _trias_shaped_report(self, mode, team=None):
        # Deliberately omits personalities + vote_pattern, so the trias checks
        # (if they run) MUST produce 'trias:'-prefixed problems.
        report = {
            "success_criterion": "x",
            "verification": "x",
            "chosen_approach": "x",
            "confidence": 0.8,
            "telemetry": {"mode": mode, "voices": {"pioneer_generator": {"tokens_in": 0}}},
            "pipeline_executed": True,
            "deliberation_log": [{"step": "aggregate", "result": {"chosen": "x"}}],
        }
        if team is not None:
            report["team"] = team
        return report

    def test_trias_mode_without_team_triggers_trias_checks(self):
        problems = validate_report.validate(self._trias_shaped_report(mode="trias"))
        self.assertTrue(
            any(p.startswith("trias:") for p in problems),
            f"trias-mode report (no team) must trigger trias checks; got {problems}",
        )

    def test_team_trias_still_triggers(self):
        problems = validate_report.validate(self._trias_shaped_report(mode="sequential", team="trias"))
        self.assertTrue(any(p.startswith("trias:") for p in problems))

    def test_sequential_mode_no_trias_checks(self):
        problems = validate_report.validate(self._trias_shaped_report(mode="sequential"))
        self.assertFalse(
            any(p.startswith("trias:") for p in problems),
            f"sequential report must NOT trigger trias checks; got {problems}",
        )


class ValidateReportCli(unittest.TestCase):
    """validate_report.main exit codes: 0 valid, 1 invalid, 2 bad JSON."""

    @staticmethod
    def _valid_report():
        return {
            "success_criterion": "x",
            "verification": "x",
            "chosen_approach": "x",
            "confidence": 0.8,
            "telemetry": {"mode": "sequential", "voices": {}},
            "pipeline_executed": True,
            "deliberation_log": [
                {"step": "generator"},
                {"step": "control"},
                {"step": "aggregate", "result": {"chosen": "x"}},
            ],
        }

    def _run_cli(self, text):
        import contextlib, io, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "report.json"
            f.write_text(text, encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = validate_report.main(["--input", str(f)])
        return rc, err.getvalue()

    def _run_report(self, report):
        import json
        return self._run_cli(json.dumps(report))

    # verifies: CONSILIUM-VALIDATE-REPORT-001#CASE-1
    def test_valid_report_exits_0(self):
        rc, _ = self._run_report(self._valid_report())
        self.assertEqual(rc, 0)

    # verifies: CONSILIUM-VALIDATE-REPORT-001#CASE-2
    def test_missing_success_criterion_exits_1_naming_field(self):
        report = self._valid_report()
        del report["success_criterion"]
        rc, err = self._run_report(report)
        self.assertEqual(rc, 1)
        self.assertIn("success_criterion", err)

    # verifies: CONSILIUM-VALIDATE-REPORT-001#CASE-3
    def test_skipped_without_skip_reason_exits_1(self):
        report = self._valid_report()
        report["skipped"] = True
        rc, err = self._run_report(report)
        self.assertEqual(rc, 1)
        self.assertIn("skip_reason", err)

    # verifies: CONSILIUM-VALIDATE-REPORT-001#CASE-4
    def test_missing_telemetry_mode_exits_1(self):
        report = self._valid_report()
        del report["telemetry"]["mode"]
        rc, err = self._run_report(report)
        self.assertEqual(rc, 1)
        self.assertIn("telemetry.mode", err)

    # verifies: CONSILIUM-VALIDATE-REPORT-001#CASE-5
    def test_malformed_json_exits_2(self):
        rc, _ = self._run_cli("{not json")
        self.assertEqual(rc, 2)


class ValidateReportSweep(unittest.TestCase):
    """validate_report.py --all: sweep a runs dir, skip dot-files, quarantine failures."""

    def test_sweep_counts_skips_dotfiles_and_quarantines(self):
        import contextlib, io, json, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            runs = Path(td)
            (runs / "bad.json").write_text(json.dumps({"success_criterion": "x"}), encoding="utf-8")
            (runs / "broken.json").write_text("{not json", encoding="utf-8")
            (runs / ".run_path_map.json").write_text("{}", encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = validate_report.sweep(runs)
            self.assertEqual(rc, 1)
            self.assertIn("checked 2, ok 0, fail 2", out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()):
                rc = validate_report.sweep(runs, quarantine=True)
            self.assertEqual(rc, 0)
            self.assertEqual(sorted(p.name for p in (runs / "_invalid").iterdir()), ["bad.json", "broken.json"])
            self.assertEqual([p.name for p in runs.glob("*.json")], [".run_path_map.json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
