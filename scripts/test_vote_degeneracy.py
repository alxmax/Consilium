"""Smoke tests for vote_degeneracy.py — the 2-0/veto split and the trias-mode gate.

Run manually (stdlib-only, no test runner):
    python scripts/test_vote_degeneracy.py

Locks the two corrections from review 2026-05-27:
  - unanimity is 3-0 ONLY; 2-0 is a veto, reported separately (not folded in)
  - only exact `"mode": "trias"` / `"trias_split"` runs are counted (no contamination
    from composite-mode runs that merely cite a vote_pattern)
"""
# tested-by: CONSILIUM-VOTE-DEGENERACY-001

from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

import plugin_paths  # puts consilium/scripts on sys.path (vote_degeneracy imports utils)

_spec = importlib.util.spec_from_file_location(
    "vote_degeneracy", plugin_paths.PLUGIN_SCRIPTS / "vote_degeneracy.py"
)
assert _spec and _spec.loader
vd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vd)


def test_unanimity_is_three_zero_only():
    r = vd.assess(Counter({"3-0": 9, "2-1": 1}), threshold=0.85, min_n=5)
    assert r["unanimity_rate"] == 0.9, r
    assert r["veto_rate"] == 0.0 and r["veto_count"] == 0, r


def test_two_zero_is_veto_not_unanimity():
    # 3 unanimous + 2 veto over n=5: unanimity is 3/5, NOT 5/5.
    r = vd.assess(Counter({"3-0": 3, "2-0": 2}), threshold=0.85, min_n=5)
    assert r["unanimity_rate"] == 0.6, r
    assert r["veto_rate"] == 0.4 and r["veto_count"] == 2, r


def test_pure_veto_has_zero_unanimity():
    r = vd.assess(Counter({"2-0": 5}), threshold=0.85, min_n=5)
    assert r["unanimity_rate"] == 0.0, r
    assert r["veto_rate"] == 1.0, r


def test_trias_mode_gate():
    assert vd.is_trias_run('{"mode": "trias"}')
    assert vd.is_trias_run('{"mode": "trias_split"}')
    # composite / non-trias modes that merely cite a vote_pattern must NOT count
    assert not vd.is_trias_run('{"mode": "trias_plus_dialectic_skeptic_defenders"}')
    assert not vd.is_trias_run('{"mode": "meta_orchestrator_2_subagents"}')
    assert not vd.is_trias_run('{"note": "vote_pattern was 3-0 in the cited run"}')


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"{len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
