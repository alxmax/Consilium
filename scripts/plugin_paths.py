"""Where the shipped plugin lives, for the dev tools and tests in scripts/.

The plugin (SKILL.md, agents/, prompts/, modes/, the runtime scripts and the
docs they cite) sits in consilium/ so that an install — the Claude plugin
directory or `apm install alxmax/Consilium/consilium` — receives only what the
skill runs. Tests, gates and repo tooling stay in scripts/ and reach the
plugin through these constants instead of `Path(__file__).parent`.

Importing this module also puts the plugin's scripts/ on sys.path, so a test
can `import aggregator` as before.

    import plugin_paths
    plugin_paths.PLUGIN_SCRIPTS / "aggregator.py"
"""
# implements: CONSILIUM-PLUGIN-FOLDER-001
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "consilium"
PLUGIN_SCRIPTS = PLUGIN_DIR / "scripts"

if str(PLUGIN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS))
