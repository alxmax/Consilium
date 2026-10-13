# Consilium

**A second opinion, structured.** Consilium is a [Claude Code](https://docs.claude.com/en/docs/claude-code) skill that evaluates a risky code change through three independent voices that don't trust each other — a creative, an analyst, and a skeptic — then aggregates their verdicts under a veto cascade into one canonical decision, with the disagreement preserved on disk.

One LLM reviewing its own proposal has predictable blind spots: it generates an idea and validates it from the same perspective. Consilium splits that into separate roles with disjoint mandates so a change is cross-examined before it ships.

The three core voices:

- **Generator** (creative) — proposes alternatives, including `do_nothing`; runs *first*, blind to risk framing (anti-anchoring)
- **Conservator** (prudent) — scores risk and reversibility; runs *second* on the candidates and sets Control's effort budget
- **Control** (analytical) — verifies correctness and writes acceptance tests

## What's interesting here

- **Adversarial-by-design deliberation** — roles with conflicting incentives, not one model agreeing with itself.
- **An 8-component veto cascade** (`consilium/scripts/aggregator.py`) that turns three voice outputs into one decision with 7 distinct routing outcomes (block / rework / adapt / escalate / aggregate).
- **A self-calibrating feedback loop** — every run lands as canonical JSON in `.consilium/runs/`, outcomes are logged to `.consilium/FEEDBACK.html`, and the next deliberation reads those priors. Confidence below a per-mode floor is flagged.
- **Cost-aware modes** — from a 1× single-context pass up to a ~2.67× three-personality vote (Trias), with a scope gate that auto-skips trivial diffs.
- **Measured, not asserted** — a benchmark harness ([Consilium-Benchmark](https://github.com/alxmax/Consilium-Benchmark), a separate repo) compares each mode against bare-model baselines on real coding/reasoning tasks with a hidden oracle. See [Benchmark results](#benchmark-results) below.
- **A CI green-gate** — every push and PR runs every unit suite, the deterministic regression scenarios (`evals/`), doc-drift invariants (`scripts/check_doc_drift.py` — the architecture explainer is parsed and checked against the code it describes), a public-leak guard, and a strict requirements-map gate. All stdlib; the CI has no `pip install` step.
- **Stdlib-only Python** — no external dependencies; each script is a small, standalone CLI with JSON I/O.

## Architecture explainer

An interactive, single-page walkthrough of the voices, pipeline, modes, voting, and the calibration loop lives at **`docs/architecture.html`** (open it in a browser). It's authored as editable React source in `docs/architecture/` — see that folder's README to preview or rebuild it.

## When to use

- PR review or diff
- Refactor planning across 2+ files
- Choosing between multiple implementation approaches
- Before committing to shared/core code
- Risk assessment for a non-trivial change

## Install

### As a plugin (one step)

```
/plugin marketplace add alxmax/Consilium
/plugin install consilium@consilium
```

This installs the `consilium` skill plus its sub-agents in a single step. The plugin is the `consilium/` folder of this repository; other agent tools can install it with [APM](https://github.com/microsoft/apm): `apm install alxmax/Consilium/consilium`. Then, in a new Claude Code session: `Review the last commit using the consilium skill`.

Deliberation state (run reports, the feedback journal, preview pages) is written to **`.consilium/`** at your project root. We recommend adding it to your `.gitignore` — it is local working state:

```gitignore
.consilium/
```

This is a preference, not a requirement: if you *want* the deliberation trail versioned alongside your code (e.g. for team review of past decisions), simply don't ignore it — everything under `.consilium/` is plain JSON/HTML and diffs cleanly.

> **Releases:** clean, tagged releases are published here for installation and review; the latest is always at the top of [Tags](https://github.com/alxmax/Consilium/tags).

## Example

Consilium reviews its own changes. Here's a **real run from this repo's history** — asking it to evaluate a three-bug fix. It prints one terminal line:

```
chosen: fix_canonical | conf: 0.57 | .consilium/runs/2026-05-29_2333_core-script-bugfixes.json
```

and writes a canonical JSON report to disk (string fields trimmed for length, all else verbatim):

```json
{
  "success_criterion": "aggregator raises a clear error on empty candidates; audit_counter uses the shared headless check; trace_graph exits cleanly on a missing file — run_evals stays green. …",
  "chosen_approach": "fix_canonical",
  "confidence": 0.57,
  "voice_scores": { "generator": 1.0, "control": 1.0, "conservator": 0.35 },
  "alternatives": [
    { "id": "do_nothing", "why_not": "control: three real defects persist" },
    { "id": "fix_agg_structured_null", "why_not": "control: returning null on malformed input masks the error; downstream must special-case" }
  ],
  "verification": "python scripts/run_evals.py (green); empty candidates → ValueError not IndexError; trace_graph --input missing.json → exit 2. …",
  "pipeline_executed": true
}
```

The chosen approach beat `do_nothing` and a plausible-but-weaker alternative — and the rejected options stay on record *with the reason they lost*. Confidence `0.57` is below the Sequential floor (`0.70`): the orchestrator retries once with the evidence that would separate the top two candidates, then asks you whether to keep the choice, pick an alternative, or rerun with Dialectic or the Skeptic. Confidence is advisory — it does not predict outcomes, so nothing re-runs automatically. Every run lands in `.consilium/runs/` (local, gitignored) and feeds the priors of the next deliberation.

## Pipeline trace

Every run records its executed path in `deliberation_log` — which steps ran, which short-circuited, and how sub-agents were dispatched. Here is the executed path for the run shown above (`fix_canonical`, Sequential mode — a 2026-05-29 run, before the Generator-first reorder), rendered as a flowchart:

```mermaid
flowchart TD
  CON["Conservator<br/>risk assessment"]
  GEN["Generator<br/>candidates"]
  CTRL["Control<br/>verdicts"]
  AGG["aggregate<br/>chosen: fix_canonical"]
  REP["report"]
  CON --> GEN
  GEN --> CTRL
  CTRL --> AGG
  AGG --> REP
```

GitHub renders Mermaid natively — paste the `--fence` output directly into any `.md` file.

## Implementation preview

One command turns a deliberation report (+ your working-tree diff) into a single self-contained HTML review page — spec, rationale, rejected alternatives, verification and per-file coloured diff, with a light/dark toggle:

```bash
git diff | python consilium/scripts/render_impl_preview.py --input .consilium/runs/<run>.json --diff-file -
```

The page lands under `.consilium/preview/` as a plain file: it survives the session and is safe to attach to a PR or hand off for review outside the CLI. In interactive Claude sessions the orchestrator also publishes it as a shareable Artifact link by default; headless/CI runs produce the file only. Opt-in only — it never gates the pipeline.

## Structure

```
Consilium/
├── consilium/           # the plugin — the only folder an install receives
│   ├── .claude-plugin/  # plugin manifest
│   ├── SKILL.md         # the contract: Constitution (4 principles) + 8-step workflow
│   ├── prompts/voices/  # per-voice role prompts (generator, control, conservator, skeptic, lenses)
│   ├── modes/           # per-mode workflow + machine-readable config (cost, sub-agents, floors)
│   ├── scripts/         # stdlib-only runtime CLIs: aggregator, confidence, priors, scope_gate, …
│   ├── agents/          # consilium-subagent — isolated dispatch via the Agent tool
│   └── docs/            # skill reference, runs schema, memory tiers
├── .claude-plugin/      # marketplace (source: ./consilium)
├── scripts/             # tests, gates and repo tooling (test_*.py, check_*.py, reqmap)
├── experiments/         # benchmarking-discipline notes + validation write-ups
├── docs/                # architecture.html explainer + its React source under docs/architecture/
├── evals/               # deterministic regression scenarios for the scripts
└── .consilium/          # local deliberation state (gitignored): runs/*.json + FEEDBACK.html
```

## Modes

| Mode | Cost | What it adds |
|------|------|--------------|
| **Sequential** (default) | 1× | Generator → Conservator → Control in one context (Generator runs first, blind to risk framing). Low confidence triggers one retry and an override prompt, never an automatic re-run |
| **Dialectic** | 1.33× | Sequential + a Skeptic sub-agent on the chosen answer, with code-context injection |
| **Trias** | ~2.67× | 3 personalities (Essentialist / Verifier / Sentinel), each running its own Sequential pass as a sub-agent, then a majority vote, then one post-vote Skeptic sub-agent on the winner |
| **`skeptic_on_chosen`** | base +1 | Composable flag over any mode — a focal Skeptic challenges the chosen answer. Opt-in (`--skeptic-on-chosen`) or on high Conservator concern — not on confidence |

For changes that are both `critical` and `irreversible`, select **Trias** explicitly — there is no automatic escalation. All dispatched voices run on Sonnet; the orchestrator runs on Opus.

**Canonical output** (validated by `consilium/scripts/validate_report.py`): JSON with `success_criterion`, `chosen_approach`, `verification`, `alternatives`, `voice_scores`, `confidence`, and a `deliberation_log`.

## Benchmark results

Snapshot 2026-06-24. Three tasks (a hard C++ coding task, a trick question whose obvious answer is a trap, a rate-math puzzle), five modes, all on **Sonnet 4.6** at high effort, graded **deterministically** against an answer key kept outside the repo — no AI judging AI, and every consilium run is verified to have actually deliberated. Two tasks sit at ceiling for every mode; the trick question is what separates them:

| Mode | Trick question (4 tries) | Coding task | Math puzzle | Avg cost / task |
|---|---|---|---|---|
| consilium_sequential | **4/4** | ✓ | ✓ ~5.7 min | $1.30 |
| consilium_dialectic | **4/4** | ✓ | ✓ ~7.3 min | $1.51 |
| consilium_trias | **3/4** | — timed out | ✓ ~9.2 min | $1.63 |
| superpowers | 2/4 | ✓ | ✓ ~42 s | $0.30 |
| **sonnet_bare** (baseline) | 1/4 | ✓ | ✓ ~38 s | $0.30 |

Same model throughout — the flip from 1/4 to 4/4 on the trick question is the deliberation *process*, not the model. The price is **~4–5× cost** and minutes instead of seconds — which is why the skill defaults to the cheapest mode and escalates on *stake* (irreversibility × magnitude), not difficulty. (Per-task cost ratios compress the pure deliberation multipliers in the Modes table — every mode also pays the same task-solving work; deliberation is the increment on top.)

Honest limits: n=4 tries per mode (a rigorous claim wants ~15); only one task is hard enough to discriminate; the Trias coding-task timeout (15-minute cap, sub-agents dispatched one at a time) is a real operational cost, not a quality result. Full write-up in the Benchmark section of `docs/architecture.html`.

## Competencies demonstrated

What this project concretely shows, in Agentic-AI / LLMOps terms. Rated **Full** (named feature, runs via a documented command, artifact in-repo), **Partial** (present but not the textbook form — caveat noted), or **n/a** (deliberately out of scope).

| Capability | Status | Where / honest caveat |
|---|---|---|
| Multi-agent orchestration | Full | 3 voices + 3 Trias personalities + Skeptic, dispatched as isolated sub-agents (`consilium/agents/`, `consilium/scripts/personalities.py`) |
| Planner / executor split | Full | orchestrator selects the mode and scope-gates, then dispatches voice executors |
| Deterministic orchestration | Full | `scope_gate → voices → aggregator → validate_report → implementation pipeline`, all stdlib scripts |
| Retry / reflection / self-healing | Full | Step 5d low-confidence retry (the orchestrator gathers discriminating evidence and re-runs the voices once), sub-agent-crash fallback, malformed-JSON retry, red→green test gate |
| Agent execution visualization | Full | the interactive architecture explainer (`docs/architecture/`) |
| Agent memory | **Partial** | 3 tiers via `memory.py` — session context, `.consilium/runs/*.json` episodic logs, `.consilium/FEEDBACK.html` outcome journal. This is **journaling + run logs, not vector / retrieval-augmented memory** |
| Token-cost telemetry | Full (instrumentation) | per-dispatch telemetry (`telemetry.voices.<name>`) recorded in every run. The explainer's tokens-per-dispatch figures are **measured** from real run telemetry (frozen snapshot, 2026-05-30 — the rollup script was retired in the 2026-06-04 dead-code triage) |
| Regression testing | Full | `evals/scenarios.json` + `run_evals.py` — deterministic subprocess tests of the scripts (not LLM-output evals) |
| Benchmarking vs baselines | Full | [Consilium-Benchmark](https://github.com/alxmax/Consilium-Benchmark) compares each mode against bare-model baselines with a hidden oracle kept out-of-tree |
| Fabrication / hallucination discipline | **Partial** | a documented independent-oracle rule for any quantitative claim (`experiments/README.md`) — a review process, not an automated metric |
| Version provenance | Full | every run stamps `telemetry.consilium_version` (`git describe`) + `consilium_ref` (the committed sha, blank on a dirty tree) — any `.consilium/runs/*.json` is reproducible via `git checkout`, and `consilium/scripts/version.py --drift <ref>` shows which prompts/modes changed since. Git is the version system — no bespoke registry |
| Framework orchestration (LangGraph / CrewAI) | n/a | evaluated and deliberately rejected — see below |
| RAG / embeddings / vector search · web backend · cloud deploy | n/a | out of scope by design — see below; targeted by a separate showcase project |

> **Why not LangGraph / CrewAI?** Evaluated and rejected on documented architectural grounds, not avoided — a 2026-05-16 deliberation chose `do_nothing` (confidence 0.36, conservative override), reaffirmed by two follow-ups on 2026-05-19. Three concrete integration shapes were proposed and scored:
>
> - **Full rewrite on LangGraph** — voices as `StateGraph` nodes calling the Anthropic API directly. Scored `risk=0.95`, control-invalid: it discards the orchestration substrate the skill is *built on* — Claude Code's sub-agent dispatch (the `Agent` tool, `agents/consilium-subagent.md`). Consilium's graph is small and fixed (Generator → Conservator → Control, fanning out to Trias/Skeptic sub-agents); that topology is already expressed as typed dispatch, not something a graph runtime would simplify.
> - **Vocabulary / diagrams only, no dependency** — rejected as cargo-culting: it borrows LangGraph's mental model with zero runtime benefit.
> - **Isolated post-hoc sidecar** (`experiments/langgraph_replay/` rendering `runs/*.json`) — the closest to viable, rejected because it would need a hard, fragile contract that `experiments/` is *never* imported by `scripts/`, to keep the dependency strictly off the runtime path.
>
> The deterministic glue (aggregator veto cascade, confidence, scope gate, `validate_report`) is already pure stdlib functions over JSON — independently runnable and testable as CLIs. State and resume are already file-based: every run persists as canonical JSON in `.consilium/runs/`, which *doubles* as episodic memory, the priors source, and the audit trail (globbed by `priors.py` / `feedback.py` / `memory.py`). A framework checkpointer would duplicate or displace that contract; a dependency tree would add supply-chain and version surface plus indirection through the authoritative `prompts/voices/*.md` — net more surface, no new capability. The deliberations are recorded in `.consilium/runs/` (local, gitignored).

> **Why not RAG / vector memory?** The retrieval surface is small and *structured*, not a corpus: priors come from globbing `.consilium/runs/*.json` and parsing `FEEDBACK.html` — tens to low-hundreds of records — and selection is by recency, `--label` substring, and OK/BAD outcome. That lookup is exact, cheap to scan in full, and fully explainable. Embeddings + an ANN index would add a vector store and an embedding-model dependency to *approximately* match over a set small enough to read exhaustively — trading a deterministic, auditable query for a fuzzy one with no recall it couldn't already get. The precondition for RAG (a large unstructured corpus) isn't present, so it stays out of scope.

## License

[Apache License 2.0](LICENSE) © 2026 Schipor Alexandru. Versions up to 1.14.0 were published under the Business Source License 1.1.

The vendored requirement-map engine (`scripts/reqmap.py`, `scripts/reqmap_engine/`, `scripts/_map_viewer.html`) comes from [requirement-manager](https://github.com/alxmax/requirement-manager), also under the Apache License 2.0 (`scripts/reqmap_engine/LICENSE`).
