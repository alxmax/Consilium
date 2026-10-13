"""Validate a Skeptic voice output against the prompts/voices/skeptic.md gate.

Reads a Skeptic verdict (JSON) from stdin. Exits 0 iff the verdict is
well-formed per the validation gate documented in
prompts/voices/skeptic.md; exits 1 (problems on stderr) if invalid —
the orchestrator then ships the original chosen unchallenged, per
modes/skeptic_on_chosen.md Step 3; exits 2 on malformed JSON.

WHY THIS EXISTS: skeptic.md describes a validation gate ("the skeptic
output is discarded ...") but until now NO code ran it — the gate was
prose only, so a malformed/under-evidenced objection could pass
unchecked (audit 2026-06-14, skeptic-adversarial-rigor ->
adversarial_enforce_gate_in_code).

ENFORCED (structural, self-contained) rules:
- can_object must be a bool.
- can_object=false -> objection must be null/absent (nothing to
  validate; ship original).
- can_object=true  -> objection is an object with:
    * concrete_concerns: list of strings; quoted_scenario: str|null
    * EVIDENCE (the core gate): >=2 non-empty concrete_concerns OR a
      non-empty quoted_scenario — anything weaker is "not enough
      evidence" and is rejected.
    * failure_mode in {correctness, goal_fit, verification_inadequate,
      meta_scope_mismatch}
    * addressable in {in_place, requires_redesign, unaddressable}
    * failure_mode=goal_fit -> at least one concrete_concern references
      "success_criterion" (skeptic.md mandates the phrasing
      "success_criterion says X but chosen does Y"); its absence is
      the fabrication signal the gate rejects.

NOT ENFORCED (need semantics + the success_criterion text, not just
shape): whether a concern is "vague", whether a cited constraint
actually appears in success_criterion, whether a
verification_inadequate scenario is genuinely specific. Those gate
rules require judgment; this validator enforces the machine-checkable
subset that previously went entirely unchecked.

Tiebreak mode (Trias B2 cascade): a verdict shaped {"tiebreak":
{"chosen": str|null, "reason": str}} is the sanctioned alternative
top-level shape (see prompts/voices/skeptic.md section "Tiebreak
mode") — chosen must be a non-empty string or null (abstain -> PEND),
reason must be non-empty.

CLI:
    cat skeptic_output.json | python scripts/validate_skeptic.py
    python scripts/validate_skeptic.py < skeptic_output.json
"""
# implements: CONSILIUM-VALIDATE-SKEPTIC-001

from __future__ import annotations

import sys

from utils import force_utf8_streams, load_json_stdin

_FAILURE_MODES = frozenset(
    {"correctness", "goal_fit", "verification_inadequate",
     "meta_scope_mismatch"}
)
_ADDRESSABLE = frozenset({"in_place", "requires_redesign", "unaddressable"})


def _validate_tiebreak(tb: object) -> list[str]:
    """Validate the B2 tiebreak selection shape (prompts/voices/skeptic.md)."""
    if not isinstance(tb, dict):
        return ["tiebreak must be an object with {chosen, reason}"]
    problems: list[str] = []
    chosen = tb.get("chosen")
    if (chosen is not None
            and (not isinstance(chosen, str) or not chosen.strip())):
        problems.append(
            "tiebreak.chosen must be a non-empty string or null (abstain)")
    reason = tb.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append("tiebreak.reason must be a non-empty string")
    return problems


def validate_skeptic(verdict: object) -> list[str]:
    if not isinstance(verdict, dict):
        return [f"skeptic output must be a JSON object, "
                f"got {type(verdict).__name__}"]

    if "tiebreak" in verdict:
        return _validate_tiebreak(verdict["tiebreak"])

    can = verdict.get("can_object")
    if not isinstance(can, bool):
        return [f"can_object must be a boolean (got {type(can).__name__})"]

    objection = verdict.get("objection")
    if can is False:
        # No objection to validate — the only inconsistency is claiming "no
        # objection" while supplying a populated one.
        if objection:
            return ["can_object=false requires objection=null"]
        return []

    # can_object is True — the objection must carry real evidence.
    problems: list[str] = []
    if not isinstance(objection, dict):
        return ["can_object=true requires an objection object"]

    concerns = objection.get("concrete_concerns")
    if concerns is not None and not isinstance(concerns, list):
        problems.append("objection.concrete_concerns must be a list")
        concerns = []
    concerns = concerns or []

    scenario = objection.get("quoted_scenario")
    if scenario is not None and not isinstance(scenario, str):
        problems.append("objection.quoted_scenario must be a string or null")
        scenario = None
    has_scenario = isinstance(scenario, str) and scenario.strip() != ""

    n_concerns = sum(1 for c in concerns if isinstance(c, str) and c.strip())
    if n_concerns < 2 and not has_scenario:
        problems.append(
            "can_object=true requires >=2 concrete_concerns OR a non-empty "
            "quoted_scenario (not enough evidence)"
        )

    failure_mode = objection.get("failure_mode")
    if failure_mode not in _FAILURE_MODES:
        problems.append(
            f"objection.failure_mode must be one of {sorted(_FAILURE_MODES)}, "
            f"got {failure_mode!r}"
        )

    addressable = objection.get("addressable")
    if addressable not in _ADDRESSABLE:
        problems.append(
            f"objection.addressable must be one of {sorted(_ADDRESSABLE)}, "
            f"got {addressable!r}"
        )

    if failure_mode == "goal_fit":
        refs_sc = any(
            isinstance(c, str) and "success_criterion" in c.lower()
            for c in concerns
        )
        if not refs_sc:
            problems.append(
                "failure_mode=goal_fit requires a concrete_concern referencing "
                "success_criterion (fabrication guard — skeptic.md mandates "
                "'success_criterion says X but chosen does Y')"
            )

    return problems


def main() -> int:
    force_utf8_streams()
    verdict = load_json_stdin("validate_skeptic.py")
    problems = validate_skeptic(verdict)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
