"""End-to-end deterministic validation of Trias lens injection.

The Trias mode biases voice perception by prepending a personality-specific
lens (`prompts/voices/<name>_lens.md`) before each voice prompt. There is no
runtime check that the lens files actually carry the bias `personalities.py`
declares — a future edit could swap two lens files and Trias would silently
produce inverted recommendations.

This test asserts the contract deterministically (without invoking the LLM):

1. **Path contract.** Every lens path declared in `personalities.PERSONALITIES`
   resolves to a readable file under repo root.
2. **Frontmatter contract.** Each lens declares `personality: <name>` and
   `voice_bias: prepended` so the orchestrator can sanity-check before dispatch.
3. **Bias-keyword contract.** Each lens contains its own expected keywords
   (Essentialist = first-principles-minimalism vocabulary, Verifier =
   testable/operational vocabulary, Sentinel = stress/silent-failure vocabulary)
   and does NOT contain the dominant keywords of the opposing personality.
   Catches accidental cross-pollination when someone edits a lens file.

CLI:
    python scripts/test_lens_bias.py            # all cases
    python scripts/test_lens_bias.py --verbose  # print PASS lines too

Exits 0 on success, 1 on first failure. Designed to be cheap enough to run
on every commit touching prompts/voices/*_lens.md.

Companion: 3 weight-invariant scenarios in evals/scenarios.json
(personalities/* family) exercise `personalities.py` output shape.
"""
# tested-by: CONSILIUM-PERSONALITIES-001
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent / "consilium"  # the shipped plugin (SKILL.md, modes/, prompts/, scripts/)

# Load personalities module via importlib so this script does not require
# being run from scripts/ on PYTHONPATH.
_spec = importlib.util.spec_from_file_location(
    "personalities", REPO_ROOT / "scripts" / "personalities.py"
)
assert _spec is not None and _spec.loader is not None
personalities = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(personalities)

# Keywords each lens MUST contain (drawn from current lens text) — case-insensitive.
# Picked to be load-bearing terms whose removal would mean the lens lost its
# distinctive bias entirely. The three fixed Trias personalities are
# Essentialist (generator-heavy), Verifier (control-heavy), Sentinel
# (conservator-heavy).
EXPECTED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "essentialist": ("first principles", "delete", "viable minimum", "earn its existence"),
    # verifies: CONSILIUM-MODE-LENS-001#AC-2
    # "skeptic carve-out" is load-bearing: it makes the Verifier lens coherent when
    # tinted onto the Skeptic voice on Dialectic's opt-in `--lens` path (internal design review
    # 2026-07-07 audit — without it the tint is a no-op that describes core-voice
    # roles the Skeptic does not occupy).
    "verifier":     ("testable", "operational", "verif", "criterion", "skeptic carve-out"),
    "sentinel":     ("stress", "silent", "counterparty", "downside"),
}

# Phrases each lens MUST NOT contain — picked so they only appear when a lens
# *endorses* the opposing bias, not when it merely names it in passing. Phrases
# here are full endorsements: "weight creative potential" only appears if a lens
# is *recommending* novelty.
FORBIDDEN_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Essentialist (generator-heavy) should not start preaching the risk lens's emphases.
    "essentialist": ("weight regression risk", "rollback ease"),
    # Verifier sits in the middle (control-heavy) — flag overt endorsements of either pole.
    "verifier":     ("tolerate moderate risk", "rollback ease"),
    # Sentinel (conservator-heavy) should not endorse the upside-chasing pole.
    "sentinel":     ("prefer ambitious", "weight creative potential"),
}


def _read_lens(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _check_frontmatter(name: str, body: str) -> list[str]:
    head = body.split("---", 2)
    if len(head) < 3:
        return [f"{name}: missing YAML frontmatter (--- delimiters)"]
    fm = head[1]
    problems: list[str] = []
    # Tolerate an optional trailing inline comment (e.g. `voice_bias: prepended  # ...`)
    # — the lens files annotate voice_bias with a `# metadata only` comment.
    if not re.search(rf"^personality:\s*{re.escape(name)}\s*(#.*)?$", fm, re.M):
        problems.append(f"{name}: frontmatter missing `personality: {name}`")
    if not re.search(r"^voice_bias:\s*prepended\s*(#.*)?$", fm, re.M):
        problems.append(f"{name}: frontmatter missing `voice_bias: prepended`")
    return problems


def _check_keywords(name: str, body: str) -> list[str]:
    lower = body.lower()
    problems: list[str] = []
    for kw in EXPECTED_KEYWORDS[name]:
        if kw not in lower:
            problems.append(
                f"{name}: expected keyword {kw!r} missing — lens lost its bias signature"
            )
    for kw in FORBIDDEN_KEYWORDS.get(name, ()):
        if kw in lower:
            problems.append(
                f"{name}: forbidden keyword {kw!r} present — possible cross-contamination"
            )
    return problems


def run_tests(verbose: bool) -> int:
    failures: list[str] = []
    passes: list[str] = []

    declared = {p["name"]: p["lens"] for p in personalities.PERSONALITIES}
    expected_names = set(EXPECTED_KEYWORDS)
    actual_names = set(declared)
    if expected_names != actual_names:
        failures.append(
            f"personalities mismatch: declared={sorted(actual_names)}, "
            f"expected={sorted(expected_names)}"
        )

    for name in sorted(expected_names & actual_names):
        rel = declared[name]
        path = REPO_ROOT / rel
        if not path.is_file():
            failures.append(f"{name}: lens path missing: {rel}")
            continue
        body = _read_lens(rel)
        if not body.strip():
            failures.append(f"{name}: lens file empty: {rel}")
            continue
        fm_problems = _check_frontmatter(name, body)
        kw_problems = _check_keywords(name, body)
        if fm_problems or kw_problems:
            failures.extend(fm_problems)
            failures.extend(kw_problems)
        else:
            passes.append(f"{name}: lens at {rel} carries expected bias signature")

    # Weight-geometry contract: the three personalities must carry distinct,
    # normalized weight vectors (generator-heavy / control-heavy / conservator-heavy)
    # so the democratic vote can diverge. A single shared vector would collapse
    # Trias to three identical voices.
    vectors = [tuple(sorted(p["weights"].items())) for p in personalities.PERSONALITIES]
    if len(set(vectors)) != len(vectors):
        failures.append("personality weight vectors are not all distinct — Trias divergence would collapse")
    else:
        passes.append("personality weight vectors are distinct")

    # telemetry.lens_applied runtime contract (validate_report.py): on a Dialectic
    # --lens run the decider and Skeptic lenses must differ, and only known lenses
    # are accepted. A missing field is the valid default — the ladder is opt-in.
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import validate_report  # noqa: E402

    personalities_names = sorted(expected_names)

    def _lens_problems(lens_applied: object) -> list[str]:
        report = {
            "success_criterion": "x", "verification": "y", "chosen_approach": "a",
            "pipeline_executed": True,
            "deliberation_log": [
                {"step": "generator", "candidates": [{"id": "a"}]},
                {"step": "aggregate", "result": {"chosen": "a"}},
            ],
            "telemetry": {"mode": "dialectic"},
        }
        if lens_applied is not None:
            report["telemetry"]["lens_applied"] = lens_applied
        return [p for p in validate_report.validate(report) if "lens_applied" in p]

    lens_cases = [
        ("decider == skeptic is rejected", {"decider": "essentialist", "skeptic": "essentialist"}, True),
        ("unknown decider lens is rejected", {"decider": "pioneer"}, True),
        ("non-object lens_applied is rejected", "essentialist", True),
        ("decider != skeptic is accepted", {"decider": "essentialist", "skeptic": "verifier"}, False),
        ("absent lens_applied (default, opt-in) is accepted", None, False),
    ]
    for label, value, should_fail in lens_cases:
        got_fail = bool(_lens_problems(value))
        (passes if got_fail == should_fail else failures).append(f"lens_applied: {label}")

    # Then-clauses of the lens_applied acceptance cases, asserted on the
    # problem text returned by validate_report._validate_telemetry itself.
    def _telemetry_problems(lens_applied: object) -> list[str]:
        return validate_report._validate_telemetry(
            {"mode": "dialectic", "lens_applied": lens_applied})

    # verifies: CONSILIUM-MODE-LENS-001#AC-1
    same = _telemetry_problems({"decider": "verifier", "skeptic": "verifier"})
    ok = any("decider" in p and "must differ" in p for p in same)
    (passes if ok else failures).append(
        "lens_applied: decider == skeptic problem states they must differ")

    # verifies: CONSILIUM-MODE-LENS-001#AC-3
    typo = _telemetry_problems({"decider": "essentailist"})
    ok = any("essentailist" in p and all(n in p for n in personalities_names)
             for p in typo)
    (passes if ok else failures).append(
        "lens_applied: unknown lens problem names the valid personalities")

    if verbose:
        for line in passes:
            print(f"PASS {line}")
    for line in failures:
        print(f"FAIL {line}", file=sys.stderr)

    total = len(passes) + len(failures)
    print(f"\n{len(passes)}/{total} passed")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true", help="print PASS lines")
    args = ap.parse_args(argv)
    return run_tests(args.verbose)


if __name__ == "__main__":
    raise SystemExit(main())

# tested-by: CONSILIUM-MODE-LENS-001
