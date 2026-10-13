"""Smoke test: Trias model assignment in personalities.py.

Validates that:
1. All 3 personalities emit a `model` field.
2. All model assignments are sonnet.
3. No personality carries schema_less.
4. CLI emits valid JSON with model fields.

CLI: python -X utf8 scripts/test_trias_model_schema.py
Exit 0 = all assertions passed.
"""
# tested-by: CONSILIUM-TRIAS-MODEL-SCHEMA-001

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent / "consilium"  # the shipped plugin (SKILL.md, modes/, prompts/, scripts/)
PERSONALITIES_PATH = REPO_ROOT / "scripts" / "personalities.py"

EXPECTED = {
    "essentialist": {"model": "sonnet", "schema_less": False},
    "verifier": {"model": "sonnet", "schema_less": False},
    "sentinel": {"model": "sonnet", "schema_less": False},
}


def _load_personalities() -> list[dict]:
    spec = importlib.util.spec_from_file_location("personalities", PERSONALITIES_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod.PERSONALITIES  # type: ignore[attr-defined]


def test_model_fields_present(personalities: list[dict]) -> None:
    for p in personalities:
        assert "model" in p, f"{p['name']}: missing 'model' field"


def test_model_assignments(personalities: list[dict]) -> None:
    by_name = {p["name"]: p for p in personalities}
    for name, expected in EXPECTED.items():
        assert name in by_name, f"personality {name!r} not found"
        actual_model = by_name[name].get("model")
        assert actual_model == expected["model"], (
            f"{name}: expected model={expected['model']!r}, got {actual_model!r}"
        )


def test_all_models_sonnet(personalities: list[dict]) -> None:
    for p in personalities:
        assert p.get("model") == "sonnet", f"{p['name']}: expected model='sonnet', got {p.get('model')!r}"


def test_no_schema_less_any_personality(personalities: list[dict]) -> None:
    for p in personalities:
        assert not p.get("schema_less"), f"{p['name']}: schema_less should be absent/False"


def test_cli_output_valid_json() -> None:
    """CLI must emit valid JSON with model fields."""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(PERSONALITIES_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"personalities.py exited {result.returncode}: {result.stderr}"
    data = json.loads(result.stdout)
    assert isinstance(data, list) and len(data) == 3
    for p in data:
        assert "model" in p, f"CLI output missing model field for {p.get('name')}"


def main() -> int:
    personalities = _load_personalities()
    tests = [
        test_model_fields_present,
        test_model_assignments,
        test_all_models_sonnet,
        test_no_schema_less_any_personality,
        test_cli_output_valid_json,
    ]
    failed = 0
    for t in tests:
        try:
            if t.__name__ == "test_cli_output_valid_json":
                t()
            else:
                t(personalities)
            print(f"[PASS] {t.__name__}")
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed += 1
    if failed:
        print(f"\n{failed}/{len(tests)} test(s) failed", file=sys.stderr)
        return 1
    print(f"\n{len(tests)}/{len(tests)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
