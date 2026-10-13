"""Regression tests for scripts/check_versions.py — the manifest version-coherence gate.

Stdlib unittest, run from the repo root:
    python scripts/test_check_versions.py
Synthesizes a throwaway repo tree in a tempdir and repoints check_versions'
module-level paths at it, so the real manifests are never touched.
"""
# tested-by: CONSILIUM-CHECK-VERSIONS-001
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path
import check_versions as CV


def _setup(d, plugin_ver="1.4.0", market_ver="1.4.0", plug_ver="1.4.0",
           engine="2026-06-26.1", plugins=None):
    d = Path(d)
    (d / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (d / "scripts" / "reqmap_engine").mkdir(parents=True, exist_ok=True)
    plugin_obj = {} if plugin_ver is None else {"version": plugin_ver}
    (d / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(plugin_obj), encoding="utf-8")
    if plugins is None:
        plugins = [{"name": "consilium", "version": plug_ver, "source": "./"}]
    (d / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"version": market_ver, "plugins": plugins}), encoding="utf-8")
    (d / "scripts" / "reqmap_engine" / "__init__.py").write_text(
        'MAP_ENGINE_VERSION = "{}"\n'.format(engine), encoding="utf-8")
    return d


class CheckVersions(unittest.TestCase):
    def _run(self, d):
        saved = (CV.REPO_ROOT, CV.PLUGIN_JSON, CV.MARKETPLACE_JSON, CV.ENGINE_VERSION_PY)
        CV.REPO_ROOT = Path(d)
        CV.PLUGIN_JSON = Path(d) / ".claude-plugin" / "plugin.json"
        CV.MARKETPLACE_JSON = Path(d) / ".claude-plugin" / "marketplace.json"
        CV.ENGINE_VERSION_PY = Path(d) / "scripts" / "reqmap_engine" / "__init__.py"
        try:
            with redirect_stdout(io.StringIO()):
                return CV.main([])
        finally:
            CV.REPO_ROOT, CV.PLUGIN_JSON, CV.MARKETPLACE_JSON, CV.ENGINE_VERSION_PY = saved

    def test_aligned_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(d)
            self.assertEqual(self._run(d), 0)

    def test_marketplace_top_level_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(d, market_ver="9.9.9")
            self.assertEqual(self._run(d), 1)

    def test_plugin_entry_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(d, plug_ver="9.9.9")
            self.assertEqual(self._run(d), 1)

    def test_missing_plugin_version_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(d, plugin_ver=None)
            self.assertEqual(self._run(d), 2)

    def test_non_dict_plugins_entry_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(d, plugins=["consilium"])   # a bare string, not an object
            self.assertEqual(self._run(d), 1)  # readable diagnostic, not AttributeError

    def test_docstring_mention_before_assignment_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(d)
            (Path(d) / "scripts" / "reqmap_engine" / "__init__.py").write_text(
                '"""example: MAP_ENGINE_VERSION = "not-a-date" """\n'
                'MAP_ENGINE_VERSION = "2026-06-26.1"\n', encoding="utf-8")
            self.assertEqual(self._run(d), 0)  # unanchored regex matched the docstring -> 1

    def test_engine_version_revision_suffix(self):
        for engine, expected in [("2026-06-03.2", 0),   # valid same-day revision
                                  ("2026-06-03.0", 1),   # .0 invalid (>= 1 required)
                                  ("2026-06-03.x", 1),   # non-numeric suffix
                                  ("2026-13-01", 1)]:    # impossible month
            with tempfile.TemporaryDirectory() as d:
                _setup(d, engine=engine)
                self.assertEqual(self._run(d), expected, "engine={!r}".format(engine))

    def test_fix_propagates_canonical_version(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(d, market_ver="1.0.0", plug_ver="1.0.0")
            saved = (CV.REPO_ROOT, CV.PLUGIN_JSON, CV.MARKETPLACE_JSON, CV.ENGINE_VERSION_PY)
            CV.REPO_ROOT = Path(d)
            CV.PLUGIN_JSON = Path(d) / ".claude-plugin" / "plugin.json"
            CV.MARKETPLACE_JSON = Path(d) / ".claude-plugin" / "marketplace.json"
            CV.ENGINE_VERSION_PY = Path(d) / "scripts" / "reqmap_engine" / "__init__.py"
            try:
                with redirect_stdout(io.StringIO()):
                    rc = CV.main(["--fix"])
            finally:
                CV.REPO_ROOT, CV.PLUGIN_JSON, CV.MARKETPLACE_JSON, CV.ENGINE_VERSION_PY = saved
            self.assertEqual(rc, 0)
            market = json.loads((Path(d) / ".claude-plugin" / "marketplace.json").read_text())
            self.assertEqual(market["version"], "1.4.0")
            self.assertEqual(market["plugins"][0]["version"], "1.4.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
