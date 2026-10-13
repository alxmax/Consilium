"""Print the CHANGELOG.md section for one version — the GitHub release notes.

The release job in .github/workflows/ci.yml cuts a `vX.Y.Z` tag and GitHub
release when consilium/.claude-plugin/plugin.json names a version that has no
release yet, and takes the notes from this script. The version-bump gate uses
the same reader, so a bump that passes CI always has notes to publish.

    python scripts/changelog_notes.py 1.15.2            # section body to stdout
    python scripts/changelog_notes.py 1.15.2 --changelog path/to/CHANGELOG.md

Exit 0 with the section body; exit 1 when CHANGELOG.md has no `## [X.Y.Z]`
heading for the version or the section is empty. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
_HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\]", re.M)


def section(text: str, version: str) -> str | None:
    """Body under `## [version]` up to the next `## [` heading, stripped."""
    headings = list(_HEADING.finditer(text))
    for i, m in enumerate(headings):
        if m.group("version") == version:
            start = text.index("\n", m.end()) + 1 if "\n" in text[m.end():] else len(text)
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            body = text[start:end].strip()
            return body or None
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", help="semver without the leading v, e.g. 1.15.2")
    ap.add_argument("--changelog", type=Path, default=DEFAULT_CHANGELOG)
    args = ap.parse_args(argv)
    body = section(args.changelog.read_text(encoding="utf-8"), args.version)
    if body is None:
        print(f"changelog_notes: no non-empty '## [{args.version}]' section in "
              f"{args.changelog}", file=sys.stderr)
        return 1
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure:  # release notes carry non-ASCII (em dashes, arrows)
        reconfigure(encoding="utf-8")
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
