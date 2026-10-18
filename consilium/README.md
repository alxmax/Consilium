# Consilium

**A second opinion, structured.** Consilium is a Claude Code skill that evaluates a risky code change through three distinct voices before you commit it (roles in one shared context by default; Trias isolates its passes in separate sub-agents):

- **Generator** proposes alternatives, always including `do_nothing`, and runs first, blind to risk framing.
- **Conservator** scores each candidate's risk and reversibility.
- **Control** verifies correctness and writes acceptance tests.

A deterministic aggregator turns the three outputs into one decision (aggregate, block, rework, adapt or escalate), scores how far the voices agree, and saves the full deliberation as a JSON report you can audit later. Opt-in modes add a Skeptic that challenges the chosen answer (Dialectic) or a three-personality vote (Trias). After a decision, an optional pipeline implements the chosen approach, writes tests and reviews the result.

## Use it

Ask in a Claude Code session, for example `Review the last commit using the consilium skill`, or run `/consilium` before a refactor, a change to shared code, or a choice between approaches.

## What it runs, reads and writes

- **Local Python scripts only.** The skill runs the stdlib-only scripts in `scripts/` (Python 3.11+, no third-party packages, nothing installed). Some call `git` read-only (`diff`, `log`, `describe`, `rev-parse`) to size the change under review.
- **No network access.** No script opens a network connection, and nothing is sent anywhere. The voices run as Claude sub-agents in your own session (`model: sonnet` by default).
- **State stays in your project.** Reports, the outcome journal and preview pages are written to `.consilium/` in the current working directory, or to the directory the `CONSILIUM_DATA_DIR` environment variable names. Add `.consilium/` to your `.gitignore` if you do not want it versioned.
- **No hooks, no permission changes.** The plugin ships one skill and two sub-agents and does not modify your settings.

## More

Architecture, modes, benchmarks and the full reference: <https://github.com/alxmax/Consilium>.

Licensed under the Apache License 2.0 (see `LICENSE`).
