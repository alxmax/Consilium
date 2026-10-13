"""Human-readable translations for deliberation report values.

Single source of truth for all user-facing natural language in Consilium
outputs.

CLI:
    python scripts/vocabulary_map.py reversibility complete
    python scripts/vocabulary_map.py magnitude critical
    python scripts/vocabulary_map.py meta_recommendation scale_down
"""
# implements: CONSILIUM-VOCABULARY-MAP-001

from __future__ import annotations

import argparse

# === ROUND2 ===
VOCABULARY_MAP: dict[str, dict] = {
    "reversibility": {
        "complete": "ușor de anulat",
        "partial": "parțial reversibil",
        "irreversible": "final, nu se mai poate schimba",
    },
    "magnitude": {
        "trivial": "consecințe mici (recuperabil în minute)",
        "moderate": "efect notabil (recuperabil în ore-zile)",
        "high": "efect important (recuperabil în luni)",
        "critical": "consecințe majore (afectează > 1 an)",
    },
    "meta_recommendation": {
        "scale_down": "question does not require extended deliberation",
        "scale_up": "question requires more attention",
        None: "",
    },
    "verdict": {
        "GO": "aprobat de majoritate",
        "MODIFY": "necesită modificări înainte de aprobare",
        "STOP": "respins de majoritate",
        "UNREACHABLE": "cvorum insuficient pentru verdict",
    },
}

TOKENS_BUDGET: dict[tuple[str, str], int] = {
    ("trivial", "complete"): 300,
    ("moderate", "partial"): 800,
    ("high", "partial"): 2000,
    ("high", "irreversible"): 2000,
    ("critical", "irreversible"): 4000,
}
_DEFAULT_BUDGET = 800
# === END ROUND2 ===


def translate(category: str, value: object) -> str:
    """Return human-readable string for a structured field value."""
    cat = VOCABULARY_MAP.get(category)
    if cat is None:
        return str(value) if value is not None else ""
    return cat.get(value, str(value) if value is not None else "")


def compute_tokens_budget(
    magnitude: str, reversibility: str, meta: str | None = None
) -> dict[str, int]:
    """Compute per-voice token budget from Conservator's Q1+Q2 outputs.

    Returns dict with keys 'generator' and 'control'.
    """
    base = TOKENS_BUDGET.get((magnitude, reversibility), _DEFAULT_BUDGET)
    if meta == "scale_down":
        base = 300
    elif meta == "scale_up":
        base = min(4000, int(base * 1.5 / 100 + 0.5) * 100)
    return {"generator": base, "control": base}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "category", help="e.g. reversibility, magnitude, meta_recommendation"
    )
    ap.add_argument(
        "value",
        nargs="?",
        default=None,
        help="e.g. complete, trivial, scale_down",
    )
    args = ap.parse_args(argv)
    print(translate(args.category, args.value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
