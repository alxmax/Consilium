---
milestone: v1.14.0
id: CONSILIUM-PLUGIN-FOLDER-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: []
risk: 1
satisfies: [ARCH-CONSILIUM-REPO-GATES-001]
---

# plugin_folder

> The plugin ships from `consilium/`, and that folder holds only what the skill runs.

## Description

Every line in this section is binding.

- An install (the Claude plugin directory, the marketplace or `apm install alxmax/Consilium/consilium`) receives only `consilium/`, the folder holding `.claude-plugin/plugin.json`.
- `consilium/` holds only `.claude-plugin/plugin.json`, `.claude-plugin/icon.png`, `SKILL.md`, `README.md`, `LICENSE` and the `agents/`, `prompts/`, `modes/`, `scripts/` and `docs/` directories.
- `consilium/scripts/` holds only Python files, and none is a test (`test_*.py`).
- No file in `consilium/` is larger than 256 KiB.
- No text file in `consilium/` runs `git push` or `git commit`, loads a remote `<script src>`, or carries an invisible format character (Unicode category Cf); such a character is written as an escape, e.g. `"\ufeff"`.
- No agent in `consilium/agents/` changes directory into `$CONSILIUM_PATH`: sub-agents call scripts by full path from the project directory, where the scripts keep their state.
- Tests, gates and repo tooling stay in `scripts/`; they reach the plugin through `scripts/plugin_paths.py`.
- `scripts/plugin_paths.py` exposes `REPO_ROOT`, `PLUGIN_DIR`, `PLUGIN_SCRIPTS`; importing it puts `PLUGIN_SCRIPTS` on `sys.path`.
- `scripts/test_plugin_folder.py` enforces these rules over the files git tracks in `consilium/`; it runs in CI and in the run-consilium driver.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given the tracked files under `consilium/`, when the allow-list is checked, then every path is one of the allowed files or lies in an allowed directory.
- **CASE-2** — Given `consilium/scripts/`, when its files are listed, then each is a `.py` file and none is named `test_*.py`.
- **CASE-3** — Given every tracked file under `consilium/`, when its size is read, then none exceeds 256 KiB.
- **CASE-4** — Given every text file under `consilium/`, when it is scanned, then none contains `git push`, `git commit` or a remote `<script src>`.
- **CASE-5** — Given every text file under `consilium/`, when it is scanned, then none contains a Unicode format (Cf) character.
- **CASE-6** — Given the agent files under `consilium/agents/`, when they are scanned, then none contains `cd "$CONSILIUM_PATH"`.
- **CASE-7** — Given the tracked files under `consilium/`, when they are listed, then `.claude-plugin/plugin.json`, `.claude-plugin/icon.png`, `SKILL.md`, `README.md` and `LICENSE` are present.

## Context (non-binding)

**Why** — the plugin directory scans and installs the whole plugin folder. When it was the repository root, every install carried tests, repo tooling, a Stop hook, git-pushing automation, CDN-loading HTML and files over 256 KiB, each of which a scan holds for review.

**Current implementation** — `scripts/plugin_paths.py`; tests in `scripts/test_plugin_folder.py`.
