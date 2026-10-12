"""Check that mode docs (modes/*.md, docs/architecture/src/*.jsx) match the
authoritative behavior in SKILL.md and scripts/confidence.py.

Stdlib-only. Exit 0 = OK, exit 1 = drift detected, exit 2 = malformed input.

Origin: design audit 2026-05-28 (an internal design audit)
found 4 discrepancies between docs/architecture/ (CV-visible explainer) and the
authoritative behavior in modes/*.md + scripts/confidence.py + SKILL.md. Track 1
(fix/docs-arch-drift-sync, commit 2114f21) fixed the 4 drifts; this script is
Track 2 — enforces the invariants so the same drifts cannot recur silently.

Prior precedent:
.consilium/runs/2026-05-25_160009-modes-dir-frontmatter-refactor.json chose YAML
frontmatter as the single source of truth for mode structured fields. That
outcome was marked OK but the 4 drifts found 3 days later proved frontmatter
alone is insufficient — the missing piece is enforcement (this script).

Each invariant has:
- `required`: a regex pattern that MUST appear in the file
- `forbidden` (optional): a regex pattern that MUST NOT appear in the file
- `source`: the authoritative source the invariant derives from

Usage:
    python -X utf8 scripts/check_doc_drift.py
"""
# implements: CONSILIUM-CHECK-DOC-DRIFT-001

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(rel_path: str) -> str:
    p = REPO_ROOT / rel_path
    if not p.exists():
        print(f"check_doc_drift: missing file {rel_path}", file=sys.stderr)
        sys.exit(2)
    return p.read_text(encoding="utf-8")


def _extract_confidence_values() -> dict[str, float | None]:
    """Parse VOTE_PATTERN_CONFIDENCE from scripts/confidence.py via AST."""
    src = _read("scripts/confidence.py")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "VOTE_PATTERN_CONFIDENCE"
                ):
                    return ast.literal_eval(node.value)
    print(
        "check_doc_drift: VOTE_PATTERN_CONFIDENCE not found in confidence.py",
        file=sys.stderr,
    )
    sys.exit(2)


def _extract_trias_jsx_outcomes() -> dict[str, float | None]:
    """Parse TRIAS_OUTCOMES rows from docs/architecture/src/trias.jsx.

    Returns {pattern: conf} where pattern is normalized to ASCII hyphens
    (jsx uses en-dash). Patterns like '3-0', '2-1', '2-0', '1-1-1', '0-0-0'.
    """
    src = _read("docs/architecture/src/trias.jsx")
    # Each row looks like:
    # { p: '2-1', label: '...', desc: '...', conf: 0.75, ...}
    # Use a tolerant regex that captures p and conf together.
    pattern = re.compile(
        r"\{\s*p:\s*['\"]([^'\"]+)['\"][^}]*?conf:\s*([0-9.]+|null)",
        re.DOTALL,
    )
    out: dict[str, float | None] = {}
    for p_raw, conf_raw in pattern.findall(src):
        p_ascii = p_raw.replace("–", "-").replace("—", "-")
        out[p_ascii] = None if conf_raw == "null" else float(conf_raw)
    return out


# ---------------------------------------------------------------------------
# Invariants (text-based)
# ---------------------------------------------------------------------------

INVARIANTS = [
    {
        "id": "trias_parallel_dispatch",
        "file": "modes/trias.md",
        "required": (
            r"[Dd]ispatch\s+all\s+3\s+personalities\s+in\s+parallel"
            r"|in\s+parallel.*personalities|parallel\s+dispatch.*personalities"
        ),
        "forbidden": (
            r"For\s+each\s+personality,\s+dispatch\s+\*\*1\s+"
            r"`consilium-subagent`\*\*"
        ),
        "source": (
            "review 2026-05-28 audit + benchmark task-08 timeout "
            "(sequential loop)"
        ),
        "rationale": (
            "Trias must dispatch 3 sub-agents in parallel; sequential loop "
            "triples wall-clock and caused task-08 to time out at 15min "
            "in n=10 benchmark."
        ),
    },
    {
        "id": "trias_parallelism_runtime_audit",
        "file": "modes/trias.md",
        "required": (
            r"benchmark/scripts/check_trias_parallelism\.py"
            r"|check_trias_parallelism\.py"
        ),
        "source": (
            "review 2026-05-28 (trias-parallelism-enforcement.json) — "
            "Reviewer 9: 'pin enforcement at orchestrator/drift-checker, "
            "NOT voice prompts'"
        ),
        "rationale": (
            "Spec prose alone has 0/6 clean-GO historical record for "
            "dispatch enforcement (per Reviewer 9 retrospective on 6 prior "
            "runs). modes/trias.md MUST reference the runtime audit script "
            "that detects serial dispatch from JSONL transcripts. Removing "
            "the audit reference without removing the parallel mandate "
            "leaves a hidden, unmeasured drift — the exact gap this "
            "invariant prevents."
        ),
    },
    {
        "id": "sequential_scale_down_skips_control",
        "file": "modes/sequential.md",
        "required": r"scale_down.*SHORT-CIRCUIT.*Skip\s+Control",
        "forbidden": r"scale_down.*Skip\s+Generator\s+AND\s+Control",
        "source": (
            "SKILL.md Step 3 + Generator-first reorder (review "
            "2026-06-13_143602 GO_WITH_CONDITIONS)"
        ),
        "rationale": (
            "Under Generator-first dispatch, Conservator runs SECOND, so "
            "scale_down can no longer skip Generator — it skips Control only "
            "(Generator already ran). The forbidden pattern guards a "
            "regression to the old Conservator-first 'skip Generator AND "
            "Control' wording."
        ),
    },
    {
        "id": "sequential_generator_first",
        "file": "modes/sequential.md",
        "required": (
            r"Default order:\s*\*\*Generator\s*→\s*Conservator\s*"
            r"→\s*Control\*\*"
        ),
        "forbidden": r"Default order:\s*\*\*Conservator\s*→\s*Generator",
        "source": (
            "review 2026-06-13_143602 GO_WITH_CONDITIONS (Generator-first "
            "reorder); Reviewer 9: pin enforcement at the drift-checker, not "
            "prose"
        ),
        "rationale": (
            "Generator now runs FIRST (blind to risk framing); the dispatch "
            "order is load-bearing (irreversibility consent moved "
            "pre-dispatch, scale_down skips Control only). Pin it so a "
            "silent regression to Conservator-first fails CI — spec prose "
            "alone has a 0/6 clean-GO record for order enforcement."
        ),
    },
    {
        "id": "build_report_emits_pipeline_executed",
        "file": "scripts/build_report.py",
        "required": r'"pipeline_executed":\s*True',
        "source": (
            "validate_report.py _validate_pipeline_executed() requires the "
            "field for non-skipped reports"
        ),
        "rationale": (
            "Trias R1 vote (Pioneer 2026-05-28): consumers of runs/*.json "
            "cannot distinguish full-pipeline runs from scale_down "
            "short-circuits without this field. build_report.py is the "
            "canonical emitter for non-skipped reports — it MUST always set "
            "pipeline_executed: True. Hand-built bypass templates "
            "(trivial-direct, prior-deliberation) set False in SKILL.md."
        ),
    },
    {
        "id": "skill_templates_have_pipeline_executed",
        "file": "SKILL.md",
        "required": r'"pipeline_executed":\s*false',
        "source": (
            "SKILL.md Step 2 scale_down short-circuit + §'Prior-deliberation "
            "passthrough' templates"
        ),
        "rationale": (
            "Bypass templates in SKILL.md (scale_down trivial-direct, "
            "prior-deliberation passthrough) construct reports by hand "
            "without build_report.py. They MUST include pipeline_executed: "
            "false so validate_report.py accepts them. If this disappears "
            "from SKILL.md, all headless scale_down runs will start failing "
            "validation silently."
        ),
    },
    {
        "id": "trias_tally_caption_confidence",
        "file": "docs/architecture/src/modes.jsx",
        "required": r"2-1\s*→\s*0\.75",
        "forbidden": r"2-1\s*→\s*0\.70",
        "source": (
            "scripts/confidence.py VOTE_PATTERN_CONFIDENCE (2-1=0.75, "
            "2-0=0.70); explainer audit 2026-05-30"
        ),
        "rationale": (
            "The Trias walkthrough tally caption in modes.jsx is prose, NOT "
            "the TRIAS_OUTCOMES table that check_trias_confidence_parity "
            "scans, so it drifted to '2-1 → 0.70' (the 2-0 value). It must "
            "state the 2-1 confidence as 0.75 to match confidence.py."
        ),
    },
    {
        "id": "explainer_voices_journey_generator_first",
        "file": "docs/architecture/src/voices.jsx",
        "required": r"Generator\s*·\s*first",
        "forbidden": r"Conservator\s*·\s*first",
        "source": (
            "Generator-first reorder (PR #416); explainer drift caught "
            "2026-06-13 — the candidate-journey SVG was still labelled "
            "'Conservator · first'"
        ),
        "rationale": (
            "The VoiceJourney SVG hardcodes which voice node sits first; "
            "reordering the JOURNEY_STEPS captions did NOT move it, so the "
            "diagram silently contradicted the Generator-first dispatch order. "
            "Pin Generator as the first node."
        ),
    },
    {
        "id": "explainer_pipeline_dispatch_generator_first",
        "file": "docs/architecture/src/pipeline.jsx",
        "required": r"Gen\s*→\s*Cons\s*→\s*Ctrl",
        "forbidden": r"Cons\s*→\s*Gen\s*→\s*Ctrl",
        "source": (
            "Generator-first reorder (PR #416); explainer dispatch-row audit "
            "2026-06-13"
        ),
        "rationale": (
            "The Sequential row in the Voices step's dispatch table must read "
            "'Gen → Cons → Ctrl'. The abbreviated-arrow form is a separate "
            "string from the section captions and slipped past earlier "
            "full-name sweeps."
        ),
    },
    {
        "id": "explainer_modes_voices_generator_first",
        "file": "docs/architecture/src/modes.jsx",
        "required": r"Gen\s*·\s*Cons\s*·\s*Ctrl",
        "forbidden": r"Cons\s*·\s*Gen\s*·\s*Ctrl",
        "source": (
            "Generator-first reorder (PR #416); explainer mode-card audit "
            "2026-06-13"
        ),
        "rationale": (
            "The mode cards' `voices:` quick-reference fields list the voice "
            "order; pin them Generator-first so a regression to 'Cons · Gen · "
            "Ctrl' fails CI."
        ),
    },
    {
        "id": "explainer_pipeline_header_generator_first",
        "file": "docs/architecture/src/pipeline.jsx",
        "required": r"CANONICAL PATH · GENERATOR-FIRST",
        "forbidden": r"CONSERVATOR-FIRST",
        "source": (
            "Generator-first reorder (PR #416); audit 2026-07-02 — the SVG "
            "header label sat outside every pinned pattern and still read "
            "'CONSERVATOR-FIRST'"
        ),
        "rationale": (
            "The headline label on the section-04 pipeline diagram states the "
            "dispatch order in its own string, separate from captions and "
            "dispatch rows. Pin it so the most visible order claim in the "
            "explainer cannot regress silently."
        ),
    },
    {
        "id": "explainer_cascade_scale_down_skips_control",
        "file": "docs/architecture/src/cascade.jsx",
        "required": r"skip Control only.*pipeline_executed:\s*false",
        "forbidden": (
            r"(?i)skip\s+Generator\s+and\s+Control|"
            r"pipeline_executed absent"
        ),
        "source": (
            "sequential_scale_down_skips_control invariant only scans "
            "modes/sequential.md; audit 2026-07-02 found the same pre-reorder "
            "wording alive in cascade.jsx"
        ),
        "rationale": (
            "The cascade table's scale_down row is a second, independent "
            "statement of the short-circuit contract. Under Generator-first it "
            "skips Control only, and the trivial-direct report must carry "
            "pipeline_executed: false (validate_report.py rejects it "
            "otherwise)."
        ),
    },
    {
        "id": "explainer_skeptic_not_confidence_triggered_modes",
        "file": "docs/architecture/src/modes.jsx",
        "required": r"--skeptic-on-chosen",
        "forbidden": r"\[0\.0,\s*0\.70?[\])]",
        "source": (
            "confidence does not predict outcomes on [confirmed] FEEDBACK rows "
            "(Brier 0.163 vs 0.085 base rate, n=64); the confidence "
            "auto-trigger was removed 2026-09-22"
        ),
        "rationale": (
            "The explainer must not describe a confidence band that fires "
            "the Skeptic; it is opt-in via --skeptic-on-chosen (plus "
            "non-confidence triggers)."
        ),
    },
    {
        "id": "explainer_skeptic_not_confidence_triggered_pipeline",
        "file": "docs/architecture/src/pipeline.jsx",
        "required": r"--skeptic-on-chosen",
        "forbidden": r"\[0\.0,\s*0\.70?[\])]",
        "source": (
            "confidence does not predict outcomes on [confirmed] FEEDBACK rows "
            "(Brier 0.163 vs 0.085 base rate, n=64); the confidence "
            "auto-trigger was removed 2026-09-22"
        ),
        "rationale": (
            "The explainer must not describe a confidence band that fires "
            "the Skeptic; it is opt-in via --skeptic-on-chosen (plus "
            "non-confidence triggers)."
        ),
    },
    {
        "id": "explainer_skeptic_not_confidence_triggered_voices",
        "file": "docs/architecture/src/voices.jsx",
        "required": r"--skeptic-on-chosen",
        "forbidden": r"\[0\.0,\s*0\.70?[\])]",
        "source": (
            "confidence does not predict outcomes on [confirmed] FEEDBACK rows "
            "(Brier 0.163 vs 0.085 base rate, n=64); the confidence "
            "auto-trigger was removed 2026-09-22"
        ),
        "rationale": (
            "The explainer must not describe a confidence band that fires "
            "the Skeptic; it is opt-in via --skeptic-on-chosen (plus "
            "non-confidence triggers)."
        ),
    },
]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_text_invariants() -> list[str]:
    failures: list[str] = []
    for inv in INVARIANTS:
        content = _read(inv["file"])
        req = inv["required"]
        if not re.search(req, content):
            failures.append(
                f"[{inv['id']}] {inv['file']}: required pattern not found\n"
                f"  pattern: {req}\n"
                f"  source:  {inv['source']}\n"
                f"  why:     {inv['rationale']}"
            )
        forbidden = inv.get("forbidden")
        if forbidden and re.search(forbidden, content):
            failures.append(
                f"[{inv['id']}] {inv['file']}: forbidden pattern present\n"
                f"  pattern: {forbidden}\n"
                f"  source:  {inv['source']}\n"
                f"  why:     {inv['rationale']}"
            )
    return failures


def check_trias_confidence_parity() -> list[str]:
    """Invariant 4: trias.jsx TRIAS_OUTCOMES must match confidence.py
    VOTE_PATTERN_CONFIDENCE."""
    failures: list[str] = []
    auth = _extract_confidence_values()
    jsx = _extract_trias_jsx_outcomes()
    # Check 2-1 and 2-0 specifically (the ones that drifted).
    for pattern in ("2-1", "2-0", "3-0"):
        if pattern not in auth:
            failures.append(
                f"[trias_confidence_parity] confidence.py missing pattern "
                f"{pattern!r}"
            )
            continue
        if pattern not in jsx:
            failures.append(
                f"[trias_confidence_parity] trias.jsx TRIAS_OUTCOMES missing "
                f"pattern {pattern!r}"
            )
            continue
        if auth[pattern] != jsx[pattern]:
            failures.append(
                f"[trias_confidence_parity] {pattern}: "
                f"confidence.py={auth[pattern]} "
                f"vs trias.jsx={jsx[pattern]}\n"
                f"  source: scripts/confidence.py VOTE_PATTERN_CONFIDENCE "
                f"(authoritative)\n"
                f"  fix:    update docs/architecture/src/trias.jsx "
                f"TRIAS_OUTCOMES + run build.py"
            )
    return failures


# ---------------------------------------------------------------------------
# Trias personality-name parity (found by the 2026-07-06 self-audit: the v3
# lens rename, PR #482, never touched the explainer or the poster generator)
# ---------------------------------------------------------------------------


def _extract_personality_names() -> set[str]:
    """AST-parse the PERSONALITIES list literal in scripts/personalities.py."""
    src = _read("scripts/personalities.py")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Name)
                        and target.id == "PERSONALITIES"):
                    personalities = ast.literal_eval(node.value)
                    return {p["name"].lower() for p in personalities}
    print("check_doc_drift: PERSONALITIES not found in personalities.py",
          file=sys.stderr)
    sys.exit(2)


def _extract_jsx_array_names(jsx_text: str, array_marker: str) -> set[str]:
    """Regex-extract `name: '...'` values from the first array literal
    that starts at `array_marker` (e.g. 'const LENSES = ['), up to its
    closing '];'."""
    start = jsx_text.find(array_marker)
    if start < 0:
        return set()
    end = jsx_text.find("];", start)
    block = jsx_text[start:end if end >= 0 else len(jsx_text)]
    return {m.lower() for m in re.findall(r"name:\s*'([^']+)'", block)}


# implements: CONSILIUM-CHECK-DOC-DRIFT-EXPLAINER-001
def check_trias_personality_name_parity() -> list[str]:
    """personalities.py is the SSOT for the 3 Trias personality names;
    the explainer (trias.jsx LENSES, modes.jsx's StageTrias
    personalities array) and the full- architecture poster generator
    must not silently drift to a retired team name."""
    failures: list[str] = []
    authoritative = _extract_personality_names()

    trias_jsx = _extract_jsx_array_names(
        _read("docs/architecture/src/trias.jsx"), "const LENSES = [")
    if trias_jsx != authoritative:
        failures.append(
            f"[trias_personality_name_parity] docs/architecture/src/trias.jsx "
            f"LENSES names "
            f"{sorted(trias_jsx)} != scripts/personalities.py "
            f"{sorted(authoritative)}\n"
            f"  fix: update trias.jsx LENSES (name + desc, matched to the new "
            f"personality's "
            f"actual lens, not just the label) and run "
            f"docs/architecture/build.py"
        )

    modes_jsx = _extract_jsx_array_names(
        _read("docs/architecture/src/modes.jsx"), "const personalities = ["
    )
    if modes_jsx != authoritative:
        failures.append(
            f"[trias_personality_name_parity] docs/architecture/src/modes.jsx "
            f"StageTrias "
            f"personalities names {sorted(modes_jsx)} != "
            f"scripts/personalities.py "
            f"{sorted(authoritative)}\n"
            f"  fix: update the personalities array in modes.jsx StageTrias "
            f"and run "
            f"docs/architecture/build.py"
        )

    poster_src = _read("scripts/make_full_architecture.py")
    poster_names = {
        m.split("\\n")[0].lower()
        for m in re.findall(r'"([A-Za-z]+)\\n\(Sequential\)"', poster_src)
    }
    if poster_names and poster_names != authoritative:
        failures.append(
            f"[trias_personality_name_parity] "
            f"scripts/make_full_architecture.py personalities_row "
            f"names {sorted(poster_names)} != scripts/personalities.py "
            f"{sorted(authoritative)}\n"
            f"  fix: update the personalities_row labels (+ the matching "
            f"*_lens.md filenames) "
            f"and re-run the script to regenerate "
            f"docs/consilium_full.{{excalidraw,html}}"
        )

    return failures


# ---------------------------------------------------------------------------
# Confidence-floor completeness (found post-#463, added 2026-06-29)
# ---------------------------------------------------------------------------


def _confidence_floor_failures(loaded: dict, fallback: dict) -> list[str]:
    """Pure comparison: floors parsed from modes/*.md vs
    confidence._FLOOR_FALLBACK.

    Factored out from check_confidence_floor_completeness so the
    comparison logic is unit-testable without importing confidence or
    touching modes/*.md on disk.
    """
    if loaded == fallback:
        return []
    missing = {k: fallback[k] for k in fallback if k not in loaded}
    unexpected = {k: loaded[k] for k in loaded if k not in fallback}
    mismatched = {
        k: f"modes={loaded[k]} vs fallback={fallback[k]}"
        for k in fallback
        if k in loaded and loaded[k] != fallback[k]
    }
    return [
        "[confidence_floor_completeness] floors parsed from modes/*.md "
        "frontmatter diverge "
        "from confidence._FLOOR_FALLBACK — a PARTIAL loss (one mode losing its "
        "`confidence_floor:`) silently disables the WEAK floor for that mode "
        "in "
        "check_mode_floor()\n"
        f"  missing (mode lost its confidence_floor): {missing}\n"
        f"  unexpected (floor present but not in fallback): {unexpected}\n"
        f"  mismatched value: {mismatched}\n"
        "  source: scripts/confidence.py _FLOOR_FALLBACK (the canonical "
        "floors)\n"
        "  fix: restore/align `confidence_floor:` in modes/<mode>.md to match "
        "_FLOOR_FALLBACK, "
        "or update _FLOOR_FALLBACK if a floor genuinely changed"
    ]


def check_confidence_floor_completeness() -> list[str]:
    """Each canonical mode's confidence_floor on disk must match
    confidence._FLOOR_FALLBACK.

    `confidence.check_mode_floor()` returns `below_floor=False` for
    any mode absent from `MODE_CONFIDENCE_FLOOR`, so a
    `modes/<mode>.md` that loses (or mis-sets) its `confidence_floor:`
    frontmatter silently disables that mode's WEAK floor. This pins
    the on-disk floors to the canonical set so any such drift fails
    CI.

    Reads each mode's floor DIRECTLY from `modes/<mode>.md` rather
    than trusting `confidence.MODE_CONFIDENCE_FLOOR`:
    `_load_mode_floors()` collapses to `_FLOOR_FALLBACK` when modes/
    is absent OR when EVERY floor is stripped, so comparing the loaded
    dict to the fallback would tautologically pass under the exact
    total-loss condition this gate must catch (review 2026-06-29,
    Reviewer 6 — a drift-checker must not silently pass when it could
    not actually check).

    Scope: this is a CI gate over the on-disk frontmatter. The runtime
    loader still falls back silently on a partial/total loss for a
    hand-edited non-CI install; the consequence there is bounded —
    the WEAK floor is advisory-only (not wired into
    aggregator/build_report).

    Intended coupling: adding a NEW mode with a `confidence_floor` (or
    changing a value) is reported as drift until `_FLOOR_FALLBACK` is
    updated in lockstep — by design (the fallback is the canonical
    complete set); the failure message names the offending mode.
    """
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import confidence as conf
    except Exception as exc:
        # an unimportable confidence module is itself drift worth failing on
        return [
            f"[confidence_floor_completeness] could not import "
            f"confidence.py: {exc}"
        ]

    modes_dir = conf._MODES_DIR
    if not modes_dir.is_dir():
        return [
            f"[confidence_floor_completeness] modes/ directory absent at "
            f"{modes_dir} — "
            "confidence_floor frontmatter cannot be validated; failing loud "
            "rather than "
            "trusting the _FLOOR_FALLBACK collapse"
        ]

    fallback = dict(conf._FLOOR_FALLBACK)
    # Read the floor declared on disk for each canonical mode.
    # sequential_scale_down has no file of its own — it inherits
    # sequential, exactly as _load_mode_floors derives it.
    loaded: dict[str, float] = {}
    for mode in fallback:
        if mode == "sequential_scale_down":
            continue
        md = modes_dir / f"{mode}.md"
        if not md.is_file():
            # absent file -> mode missing from `loaded` -> reported as
            # drift below
            continue
        fm = conf._parse_frontmatter(md.read_text(encoding="utf-8"))
        raw = fm.get("confidence_floor", "").strip()
        if raw and raw != "N/A":
            try:
                loaded[mode] = float(raw)
            except ValueError:
                pass
    if "sequential" in loaded:
        loaded["sequential_scale_down"] = loaded["sequential"]
    return _confidence_floor_failures(loaded, fallback)


# ---------------------------------------------------------------------------
# Legacy MODE enum removal milestone (Reviewer 9 R1 pattern D)
# ---------------------------------------------------------------------------

REMOVAL_MILESTONES: dict[str, str] = {
    # alias -> dated removal milestone (ISO date). Removed after that date.
    # parallel_skeptic/dialectic_skeptic: original 2026-08-17 milestone passed
    # with no removal work scheduled — extended 2026-08-18, +3mo.
    "parallel_skeptic": "2026-11-17",
    "dialectic_skeptic": "2026-11-17",
}


def check_legacy_mode_milestone() -> list[str]:
    """Verify legacy MODE aliases in validate_report.py carry a dated
    removal note.

    Also enforces the milestone itself: once the date has passed, a lingering
    alias fails the gate (audit 2026-07-02 — previously the dates were
    decorative and would silently expire).
    """
    from datetime import date

    failures: list[str] = []
    src = _read("scripts/validate_report.py")
    today = date.today().isoformat()
    for alias, milestone_date in REMOVAL_MILESTONES.items():
        if alias not in src:
            # Already removed — that's fine, milestone reached.
            continue
        if today > milestone_date:
            failures.append(
                f"[legacy_mode_milestone] {alias!r}: removal milestone "
                f"{milestone_date} has passed "
                f"but the alias is still present in validate_report.py\n"
                f"  fix: remove the alias (+ its doc mentions), or extend the "
                f"milestone in "
                f"REMOVAL_MILESTONES with a dated rationale"
            )
            continue
        # Require a comment containing the milestone date near the alias line.
        # Tolerant: the date must appear within 200 chars of the alias literal.
        idx = src.find(f'"{alias}"')
        if idx < 0:
            continue
        window = src[max(0, idx - 200): idx + 200]
        if milestone_date not in window:
            failures.append(
                f"[legacy_mode_milestone] {alias!r}: removal date "
                f"{milestone_date} not declared\n"
                f"  fix: add comment '# remove after {milestone_date}' "
                f"adjacent to the alias entry"
            )
    return failures


# ---------------------------------------------------------------------------
# Test-suite coverage (audit 2026-05-31)
# ---------------------------------------------------------------------------


def check_test_suite_coverage() -> list[str]:
    """Every scripts/test_*.py must be gated in BOTH ci.yml and the
    run-consilium driver.

    Prevents the test-drift class that let test_lens_bias.py sit RED
    on `main` unnoticed (audit 2026-05-31): a suite present on disk
    that no gate runs. Keeps the explicit named CI steps — this only
    fails the build if a suite is added without being wired into both
    gates.
    """
    failures: list[str] = []
    test_files = sorted(
        p.name for p in (REPO_ROOT / "scripts").glob("test_*.py"))
    if not test_files:
        return failures

    def _active(text: str) -> str:
        # GAP#2: ignore comment-only lines so a commented-out gating step
        # ('# run: python scripts/test_x.py') or a name mentioned only in a
        # comment no longer counts as coverage — the bare substring check was
        # blind to whether a suite is actually INVOKED vs merely MENTIONED.
        return "\n".join(
            l for l in text.splitlines() if not l.lstrip().startswith("#"))

    ci = _active(_read(".github/workflows/ci.yml"))
    driver = _active(_read(".claude/skills/run-consilium/driver.py"))
    for name in test_files:
        if name not in ci:
            failures.append(
                f"[test_suite_coverage] {name} is not gated in "
                f".github/workflows/ci.yml\n"
                f"  fix: add a step `run: python scripts/{name}` to the "
                f"green-gate job"
            )
        if name not in driver:
            failures.append(
                f"[test_suite_coverage] {name} is not gated in run-consilium "
                f"driver.py smoke()\n"
                f"  fix: add {name!r} to the test-suite loop in smoke()"
            )
    return failures


# ---------------------------------------------------------------------------
# Referenced-script existence (audit 2026-06-10)
# ---------------------------------------------------------------------------

# Normative docs: files whose scripts/<name>.py references are contracts the
# orchestrator executes, not historical mentions. CHANGELOG.md and docs/archive/
# are deliberately excluded (historical context may cite retired scripts).
SCRIPT_REF_DOCS = [
    "SKILL.md",
    "CLAUDE.md",
    "README.md",
    "docs/runs-schema.md",
    ".claude/skills/run-consilium/SKILL.md",
]

# Literal scripts/<name>.py paths (subdirs like deprecated/ allowed). The
# lookbehind rejects benchmark/scripts/... and other prefixed paths; wildcard
# patterns like scripts/test_*.py never match because '*' is outside the class.
_SCRIPT_REF_RE = re.compile(r"(?<![\w/\-.])scripts/[A-Za-z0-9_/]+\.py")


def check_referenced_scripts_exist() -> list[str]:
    """Every literal scripts/<name>.py referenced in a normative doc must exist.

    Origin: the 2026-06-04 dead-code triage (commit 84632db) deleted 13 scripts
    flagged "dead" by static reference analysis — blind to scripts invoked via
    SKILL.md prose. SKILL.md kept mandating audit_feedback.py/usage.py/
    efficiency.py/trace_graph.py for 6 days (audit 2026-06-10). This invariant
    makes any future deletion-vs-contract divergence fail CI immediately.
    """
    failures: list[str] = []
    doc_files = list(SCRIPT_REF_DOCS) + sorted(
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for p in (REPO_ROOT / "modes").glob("*.md")
    )
    for rel in doc_files:
        content = _read(rel)
        for ref in sorted(set(_SCRIPT_REF_RE.findall(content))):
            if not (REPO_ROOT / ref).exists():
                failures.append(
                    f"[referenced_script_exists] {rel}: references {ref} which "
                    f"does not exist\n"
                    f"  fix: restore the script, or rewrite/remove the "
                    f"reference — a normative\n"
                    f"  doc must not instruct the orchestrator to run a "
                    f"deleted script"
                )
    return failures


# Literal prompts/voices|modes|agents/<name>.md paths, plus bare
# `<name>_lens.md` (SKILL.md names lenses without their directory).
# Placeholders like modes/<mode>.md never match because '<' is
# outside the class.
_CONTRACT_REF_RE = re.compile(
    r"(?<![\w/\-.])(?:prompts/voices|modes|agents)/[A-Za-z0-9_\-]+\.md")
_LENS_REF_RE = re.compile(r"(?<![\w/\-.])([a-z]+_lens\.md)")


def check_referenced_contracts_exist() -> list[str]:
    """Every voice/mode/agent prompt a normative doc references must exist.

    Origin: SKILL.md Step 0 kept naming pioneer/architect/steward_lens.md after
    PR #482 replaced them with essentialist/verifier/sentinel — the orchestrator
    was told to read files that no longer existed, and referenced_script_exists
    did not see it because it only covers scripts/*.py.
    """
    failures: list[str] = []
    doc_files = list(SCRIPT_REF_DOCS) + sorted(
        str(p.relative_to(REPO_ROOT)).replace("\\", "/")
        for d in ("modes", "agents", "prompts/voices")
        for p in (REPO_ROOT / d).glob("*.md")
    )
    for rel in doc_files:
        content = _read(rel)
        refs = set(_CONTRACT_REF_RE.findall(content))
        refs |= {
            f"prompts/voices/{name}" for name in _LENS_REF_RE.findall(content)
        }
        for ref in sorted(refs):
            if not (REPO_ROOT / ref).exists():
                failures.append(
                    f"[referenced_contract_exists] {rel}: references {ref} "
                    f"which does not exist\n"
                    f"  fix: point the reference at the current prompt file, "
                    f"or remove it"
                )
    return failures


# SKILL.md is loaded on every deliberation, so its size is a per-run token cost.
# Reference material belongs in docs/skill-reference.md, linked from the step.
SKILL_MD_MAX_BYTES = 32_000


def check_skill_md_size() -> list[str]:
    size = len(_read("SKILL.md").encode("utf-8"))
    if size <= SKILL_MD_MAX_BYTES:
        return []
    return [
        f"[skill_md_size] SKILL.md is {size:,} bytes (ceiling "
        f"{SKILL_MD_MAX_BYTES:,})\n"
        f"  fix: move reference material to docs/skill-reference.md and link "
        f"it from the step"
    ]


# ---------------------------------------------------------------------------
# CI_CHECKS <-> ci.yml completeness (2026-07-06 Trias self-audit finding)
# ---------------------------------------------------------------------------

# Steps with no scripts/*.py or build.py reference (pure bash /
# inline `python -c`) that are nonetheless covered by an existing
# CI_CHECKS card -- named explicitly so the exception is visible in a
# diff, not a silent gap. Add an entry here ONLY alongside the
# CI_CHECKS card it references.
ALLOWED_OUT_OF_SCOPE_CI_STEPS: dict[str, str] = {
    "Version bump has a matching CHANGELOG entry":
        "covered by the 'Manifest & changelog gate' CI_CHECKS card together "
        "with "
        "Manifest version coherence",
}

_CI_STEP_SPLIT_RE = re.compile(r"\n(?=\s{6}- (?:name|uses):)")
_CI_SCRIPT_TOKEN_RE = re.compile(
    r"scripts/[A-Za-z0-9_/]+\.py|docs/architecture/build\.py")


def _parse_ci_named_steps(ci_yaml_text: str) -> list[tuple[str, str]]:
    """Text-based parse of the green-gate job's steps: (name, run_text)
    for every step that declares a `name:` field. Steps using only
    `uses:` (actions/checkout, actions/setup-python) carry no
    human-readable label and are dropped by construction -- not
    specially allowlisted."""
    steps: list[tuple[str, str]] = []
    for chunk in _CI_STEP_SPLIT_RE.split(ci_yaml_text):
        m = re.match(r"\s*-\s*name:\s*(.+)", chunk)
        if not m:
            continue
        name = m.group(1).strip()
        run_m = re.search(r"run:\s*\|?[ \t]*\n?(.*)", chunk, re.DOTALL)
        run_text = run_m.group(1) if run_m else ""
        steps.append((name, run_text))
    return steps


# implements: CONSILIUM-CHECK-DOC-DRIFT-EXPLAINER-001
def _ci_checks_completeness_failures(
    ci_yaml_text: str, extras_jsx_text: str
) -> list[str]:
    """Pure comparison: every non-test ci.yml step must have a
    matching CI_CHECKS card (by exact scripts/*.py or build.py
    basename) or an explicit ALLOWED_OUT_OF_SCOPE_CI_STEPS entry.
    Matches on the script's basename, not the full run-line, so 2
    steps sharing one script (e.g. a `gate` and a `sync --check` step
    on one script) correctly resolve to 1 card. Skeptic finding,
    2026-07-06 Trias self-audit: free-text substring matching on the
    full run-line either false-fails on that already-correct grouping,
    or (matching only bare filenames) is too loose to catch a real
    drift."""
    block = re.search(
        r"const CI_CHECKS = \[(.*?)\n\s*\];", extras_jsx_text, re.DOTALL)
    if not block:
        return [
            "[ci_checks_completeness] docs/architecture/src/extras.jsx: "
            "CI_CHECKS array not found"
        ]
    cards_text = block.group(1)

    failures: list[str] = []
    for name, run_text in _parse_ci_named_steps(ci_yaml_text):
        token = _CI_SCRIPT_TOKEN_RE.search(run_text)
        if not token:
            if name not in ALLOWED_OUT_OF_SCOPE_CI_STEPS:
                failures.append(
                    f"[ci_checks_completeness] ci.yml step {name!r} has no "
                    f"scripts/*.py or "
                    f"build.py reference and no ALLOWED_OUT_OF_SCOPE_CI_STEPS "
                    f"entry\n"
                    f"  fix: add a docs/architecture/src/extras.jsx CI_CHECKS "
                    f"card, or an "
                    f"explicit ALLOWED_OUT_OF_SCOPE_CI_STEPS entry naming the "
                    f"covering card"
                )
            continue
        basename = token.group(0).rsplit("/", 1)[-1]
        if re.match(r"test_.*\.py$", basename):
            continue  # covered generically by the 'Unit suites' card
        if basename not in cards_text:
            failures.append(
                f"[ci_checks_completeness] ci.yml step {name!r} runs "
                f"{basename!r} but no "
                f"CI_CHECKS card in docs/architecture/src/extras.jsx mentions "
                f"it\n"
                f"  fix: add a card naming {basename!r} (or an "
                f"ALLOWED_OUT_OF_SCOPE_CI_STEPS "
                f"entry) and re-run docs/architecture/build.py"
            )
    return failures


def check_ci_checks_completeness() -> list[str]:
    ci_yaml_text = _read(".github/workflows/ci.yml")
    extras_jsx_text = _read("docs/architecture/src/extras.jsx")
    return _ci_checks_completeness_failures(ci_yaml_text, extras_jsx_text)


# ---------------------------------------------------------------------------
# Trias spec alignment (cost_multiplier / subagents parity)
# ---------------------------------------------------------------------------

# Explicit format-mapping: do not use f'{v}×' — avoids silent float→str bugs.
_COST_FMT: dict[float, str] = {
    4.0: '4×', 3.0: '3×', 2.67: '2.67×', 1.33: '1.33×', 1.0: '1×', 1.1: '1.1×'
}


def _parse_trias_frontmatter() -> dict[str, float | int]:
    """Return {cost_multiplier, subagents, dispatch_count_worst_case}
    from modes/trias.md YAML."""
    src = _read("modes/trias.md")
    fm = re.search(r'^---\n(.*?)\n---', src, re.DOTALL | re.MULTILINE)
    if not fm:
        print("check_doc_drift: modes/trias.md has no YAML frontmatter",
              file=sys.stderr)
        sys.exit(2)
    text = fm.group(1)
    out: dict[str, float | int] = {}
    for key, cast in (
        ("cost_multiplier", float),
        ("subagents", int),
        ("dispatch_count_worst_case", int),
    ):
        m = re.search(rf'^{key}:\s*([0-9.]+)', text, re.MULTILINE)
        if not m:
            print(
                f"check_doc_drift: modes/trias.md frontmatter missing "
                f"'{key}'",
                file=sys.stderr)
            sys.exit(2)
        out[key] = cast(m.group(1))  # type: ignore[operator]
    return out


def check_trias_spec_alignment() -> list[str]:
    """Trias cost/sub-agent counts must match modes/trias.md
    frontmatter (the SSOT).

    Each file is checked independently so the failure message names
    exactly which file drifted. Format mapping uses _COST_FMT
    (explicit dict, not string coercion).

    Origin: Trias deliberation 2026-06-12 (fix_all_plus_invariant,
    confidence 0.75).
    """
    failures: list[str] = []
    fm = _parse_trias_frontmatter()
    cost_multiplier: float = fm["cost_multiplier"]  # type: ignore[assignment]
    subagents: int = fm["subagents"]  # type: ignore[assignment]
    # type: ignore[assignment]
    worst_case: int = fm["dispatch_count_worst_case"]
    cost_fmt = _COST_FMT.get(cost_multiplier)
    if cost_fmt is None:
        failures.append(
            f"[trias_spec_alignment] modes/trias.md "
            f"cost_multiplier={cost_multiplier} "
            f"has no entry in _COST_FMT — add it before updating"
        )
        return failures

    # -- efficiency-section.jsx: MODES_DATA trias row --
    eff = _read("docs/architecture/src/efficiency-section.jsx")
    if f"costMultiplier: '{cost_fmt}'" not in eff:
        failures.append(
            f"[trias_spec_alignment] efficiency-section.jsx MODES_DATA trias "
            f"row: "
            f"costMultiplier must be '{cost_fmt}' (modes/trias.md "
            f"cost_multiplier={cost_multiplier})\n"
            f"  fix: update the trias MODES_DATA entry and run "
            f"docs/architecture/build.py"
        )
    if f"dispatches: {subagents}" not in eff:
        failures.append(
            f"[trias_spec_alignment] efficiency-section.jsx MODES_DATA trias "
            f"row: "
            f"dispatches must be {subagents} (modes/trias.md "
            f"subagents={subagents})\n"
            f"  fix: update the trias MODES_DATA entry and run "
            f"docs/architecture/build.py"
        )

    failures += _trias_extras_jsx_failures(cost_fmt, subagents)
    failures += _trias_modes_jsx_failures(cost_fmt, worst_case)
    failures += _trias_claude_md_failures(cost_multiplier, subagents)
    return failures


def _trias_extras_jsx_failures(cost_fmt: str, subagents: int) -> list[str]:
    """extras.jsx CostScatter TRI entry and CostBars trias row."""
    failures: list[str] = []
    ext = _read("docs/architecture/src/extras.jsx")
    # TRI entry must carry the correct cost label
    tri_match = re.search(r"id:\s*'TRI'[^}]*?cost:\s*'([^']+)'", ext, re.DOTALL)
    if not tri_match or tri_match.group(1) != cost_fmt:
        found = tri_match.group(1) if tri_match else "not found"
        failures.append(
            f"[trias_spec_alignment] extras.jsx CostScatter TRI: "
            f"cost must be '{cost_fmt}', got '{found}'\n"
            f"  fix: update MODES_PLOT TRI entry and run "
            f"docs/architecture/build.py"
        )

    # -- extras.jsx CostBars trias row: label and subagents --
    cbars_match = re.search(
        r"name:\s*'trias'[^}]*?label:\s*'([^']+)'", ext, re.DOTALL)
    if not cbars_match or cbars_match.group(1) != cost_fmt:
        found = cbars_match.group(1) if cbars_match else "not found"
        failures.append(
            f"[trias_spec_alignment] extras.jsx CostBars trias row: "
            f"label must be '{cost_fmt}', got '{found}'\n"
            f"  fix: update ROWS trias entry and run docs/architecture/build.py"
        )
    cbars_sub = re.search(
        r"name:\s*'trias'[^}]*?subagents:\s*([0-9]+)", ext, re.DOTALL)
    if not cbars_sub or int(cbars_sub.group(1)) != subagents:
        found = cbars_sub.group(1) if cbars_sub else "not found"
        failures.append(
            f"[trias_spec_alignment] extras.jsx CostBars trias row: "
            f"subagents must be {subagents}, got {found}\n"
            f"  fix: update ROWS trias entry and run docs/architecture/build.py"
        )
    return failures


def _trias_modes_jsx_failures(cost_fmt: str, worst_case: int) -> list[str]:
    """modes.jsx trias cost and worst-case sub-agent count."""
    failures: list[str] = []
    modes_jsx = _read("docs/architecture/src/modes.jsx")
    modes_trias_cost = re.search(
        r"id:\s*'trias'[\s\S]*?cost:\s*'([^']+)'", modes_jsx, re.DOTALL
    )
    if (not modes_trias_cost
            or not modes_trias_cost.group(1).startswith(cost_fmt)):
        found = modes_trias_cost.group(1) if modes_trias_cost else "not found"
        failures.append(
            f"[trias_spec_alignment] modes.jsx trias cost entry: "
            f"must start with '{cost_fmt}', got '{found}'\n"
            f"  fix: update MODES trias cost field and run "
            f"docs/architecture/build.py"
        )
    if f"{worst_case} sub-agents" not in modes_jsx:
        failures.append(
            f"[trias_spec_alignment] modes.jsx: worst-case '{worst_case} "
            f"sub-agents' not found\n"
            f"  fix: update MODES trias cost field (worst case) and run "
            f"docs/architecture/build.py"
        )
    return failures


def _trias_claude_md_failures(
        cost_multiplier: float, subagents: int) -> list[str]:
    """CLAUDE.md: Trias entry must not carry the pre-Skeptic
    sub-agent count."""
    failures: list[str] = []
    # When cost_multiplier is 4.0 (Skeptics added), the old count was
    # 3 sub-agents.
    # 2.67 -> '6' added 2026-07-02: the 6->4 skeptic-lever redesign changed the
    # cost without extending this dict, leaving the guard inert (audit finding).
    stale_count_by_cost: dict[float, str] = {4.0: '3', 3.0: '9', 2.67: '6'}
    stale_count = stale_count_by_cost.get(cost_multiplier)
    if stale_count:
        claude = _read("CLAUDE.md")
        trias_line = re.search(r'\*\*Trias\*\*.*', claude)
        if trias_line and f'({stale_count} sub-agents)' in trias_line.group(0):
            failures.append(
                f"[trias_spec_alignment] CLAUDE.md: Trias entry has stale "
                f"'({stale_count} sub-agents)' — must reflect {subagents} "
                f"sub-agents\n"
                f"  fix: update the Trias bullet in the 'Available modes' "
                f"section"
            )
    return failures


# ---------------------------------------------------------------------------
# Implement-pipeline spec alignment (found 2026-07-06: the explainer's "Code
# integration pipeline" section never stated its own subagent count / cost)
# ---------------------------------------------------------------------------


# implements: CONSILIUM-CHECK-DOC-DRIFT-EXPLAINER-001
def check_implement_pipeline_spec_alignment() -> list[str]:
    """modes/implement_pipeline.md's `subagents`/`cost_multiplier`
    frontmatter must be stated explicitly in extras.jsx's
    ImplementSection GATE_ITEMS -- mirrors
    check_trias_spec_alignment's pattern, scoped to the one section
    that was found to omit its own headline stats (every other
    mode/flag states cost + subagent count explicitly in modes.jsx's
    MODES array; ImplementSection is a different component,
    GATE_ITEMS, which had no equivalent line)."""
    src = _read("modes/implement_pipeline.md")
    fm = re.search(r'^---\n(.*?)\n---', src, re.DOTALL | re.MULTILINE)
    if not fm:
        print(
            "check_doc_drift: modes/implement_pipeline.md has no YAML "
            "frontmatter",
            file=sys.stderr)
        sys.exit(2)
    text = fm.group(1)
    m_sub = re.search(r'^subagents:\s*([0-9]+)', text, re.MULTILINE)
    m_cost = re.search(r'^cost_multiplier:\s*([0-9.]+)', text, re.MULTILINE)
    if not m_sub or not m_cost:
        print(
            "check_doc_drift: modes/implement_pipeline.md frontmatter "
            "missing subagents/cost_multiplier",
            file=sys.stderr)
        sys.exit(2)
    subagents = int(m_sub.group(1))
    cost_multiplier = float(m_cost.group(1))

    cost_fmt = _COST_FMT.get(cost_multiplier)
    if cost_fmt is None:
        return [
            f"[implement_pipeline_spec_alignment] modes/implement_pipeline.md "
            f"cost_multiplier="
            f"{cost_multiplier} has no entry in _COST_FMT — add it before "
            f"updating"
        ]

    ext = _read("docs/architecture/src/extras.jsx")
    block = re.search(r'const GATE_ITEMS = \[(.*?)\n\s*\];', ext, re.DOTALL)
    gate_text = block.group(1) if block else ""

    failures: list[str] = []
    if f"{subagents} sub-agent" not in gate_text:
        failures.append(
            f"[implement_pipeline_spec_alignment] extras.jsx GATE_ITEMS does "
            f"not state "
            f"'{subagents} sub-agent(s)' (modes/implement_pipeline.md "
            f"subagents={subagents})\n"
            f"  fix: state the sub-agent count in ImplementSection's "
            f"GATE_ITEMS and run "
            f"docs/architecture/build.py"
        )
    if cost_fmt not in gate_text:
        failures.append(
            f"[implement_pipeline_spec_alignment] extras.jsx GATE_ITEMS does "
            f"not state "
            f"'{cost_fmt}' (modes/implement_pipeline.md "
            f"cost_multiplier={cost_multiplier})\n"
            f"  fix: state the cost multiplier in ImplementSection's "
            f"GATE_ITEMS and run "
            f"docs/architecture/build.py"
        )
    return failures


# ---------------------------------------------------------------------------
# validate_report literal parity (audit GAP#4, 2026-06-14)
# ---------------------------------------------------------------------------


def check_validate_report_vote_pattern_parity() -> list[str]:
    """validate_report's Trias vote-pattern literals must match confidence.py.

    validate_report HAND-COPIES the canonical Trias vote patterns
    rather than importing them — importing confidence would pull in
    its modes/*.md load at import time (MODE_CONFIDENCE_FLOOR), and
    validate_report is a fast stdin gate. This invariant keeps the
    hand-copied literals in lockstep with the SSOT so they cannot
    silently diverge (audit GAP#4). check_trias_confidence_parity
    guards the *doc* (trias.jsx) values; this guards the *gate*
    (validate_report) key sets. validate_report is import-light (no
    confidence import), so reading its runtime values here does NOT
    trigger the modes/*.md load.
    """
    conf = _extract_confidence_values()
    conf_all = set(conf)
    conf_null = {k for k, v in conf.items() if v is None}

    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        import validate_report as vr
    except Exception as exc:
        # an unimportable validator is itself drift worth failing on
        return [
            f"[validate_report_parity] could not import "
            f"validate_report.py: {exc}"
        ]

    failures: list[str] = []
    vr_all = set(vr._TRIAS_VOTE_PATTERNS)
    vr_null = set(vr._TRIAS_NULL_PATTERNS)
    if vr_all != conf_all:
        failures.append(
            f"[validate_report_parity] _TRIAS_VOTE_PATTERNS {sorted(vr_all)} "
            f"!= "
            f"confidence.VOTE_PATTERN_CONFIDENCE keys {sorted(conf_all)}\n"
            f"  fix: update validate_report._TRIAS_VOTE_PATTERNS to match "
            f"confidence.py"
        )
    if vr_null != conf_null:
        failures.append(
            f"[validate_report_parity] _TRIAS_NULL_PATTERNS {sorted(vr_null)} "
            f"!= "
            f"confidence null-confidence patterns {sorted(conf_null)}\n"
            f"  fix: update validate_report._TRIAS_NULL_PATTERNS to match "
            f"confidence.py"
        )
    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    all_failures: list[str] = []
    all_failures.extend(check_text_invariants())
    all_failures.extend(check_trias_confidence_parity())
    all_failures.extend(check_trias_personality_name_parity())
    all_failures.extend(check_confidence_floor_completeness())
    all_failures.extend(check_validate_report_vote_pattern_parity())
    all_failures.extend(check_trias_spec_alignment())
    all_failures.extend(check_legacy_mode_milestone())
    all_failures.extend(check_test_suite_coverage())
    all_failures.extend(check_referenced_scripts_exist())
    all_failures.extend(check_referenced_contracts_exist())
    all_failures.extend(check_skill_md_size())
    all_failures.extend(check_ci_checks_completeness())
    all_failures.extend(check_implement_pipeline_spec_alignment())

    if not all_failures:
        print("doc-drift OK: all invariants hold", flush=True)
        return 0

    print(f"doc-drift FAIL: {len(all_failures)} invariant(s) violated",
          file=sys.stderr)
    for i, f in enumerate(all_failures, 1):
        print(f"\n{i}. {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
