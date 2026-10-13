"""Regression tests for probe_change path decoding (the security-gate fix).

Run: python scripts/test_probe_change.py   (exit 0 = all pass, 1 = a failure)

Origin: 2026-05-31 audit Critical — git C-quotes paths with non-ASCII/space/
control bytes (e.g. ``"auth/fi\\305\\237ier.py"``). Left verbatim, the leading
double-quote defeats blocklist prefix/glob matching, silently downgrading a
critical change (auth/, migrations/, ...) to trivial. ``_unquote_git_path``
decodes the C-quoted form back to a plain UTF-8 path so the blocklist sees the
real prefix; ``parse_numstat`` applies it per line.

This guards the ACTUAL fixed code: it calls _unquote_git_path / parse_numstat
directly. A scope_gate --signals-stdin scenario would NOT — it injects
pre-parsed signals and bypasses the parser entirely (false coverage).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import plugin_paths  # noqa: E402,F401 — puts consilium/scripts on sys.path
from probe_change import _unquote_git_path, parse_numstat  # noqa: E402

# git emits a C-quoted path as the literal 4 chars: backslash, 3, 0, 5 ...
# In a Python literal that is "\\305". Octal \305\237 = UTF-8 0xC5 0x9F = U+015F (ş).
QUOTED_OCTAL = '"auth/fi\\305\\237ier.py"'
DECODED = "auth/fişier.py"


def run() -> int:
    passed = failed = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        ok = bool(cond)
        passed += ok
        failed += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else '  -> ' + detail}")

    # 1. Plain ASCII path is returned unchanged.
    check("plain path unchanged", _unquote_git_path("src/foo.py") == "src/foo.py",
          repr(_unquote_git_path("src/foo.py")))

    # 2. A quoted path with a space has its wrapping quotes stripped.
    check("quoted space path unquoted", _unquote_git_path('"my dir/file.py"') == "my dir/file.py",
          repr(_unquote_git_path('"my dir/file.py"')))

    # 3. THE FIX: an octal C-quoted non-ASCII path decodes to the real UTF-8 path,
    #    with no leading quote, so the blocklist prefix is matchable again.
    decoded = _unquote_git_path(QUOTED_OCTAL)
    check("octal C-quoted path decodes to UTF-8", decoded == DECODED, repr(decoded))
    check("decoded path exposes the auth/ blocklist prefix",
          decoded.startswith("auth/") and '"' not in decoded, repr(decoded))

    # 4. Malformed escape that fails to decode falls back to the raw input
    #    (octal \200 = lone 0x80 continuation byte, invalid as UTF-8 start).
    bad = '"\\200"'
    check("undecodable quoted path falls back to input", _unquote_git_path(bad) == bad,
          repr(_unquote_git_path(bad)))

    # 5. Integration: parse_numstat surfaces the decoded path, not the quoted form,
    #    so the security gate that scans `paths` sees `auth/...`.
    summary, paths = parse_numstat(f"1\t0\t{QUOTED_OCTAL}\n")
    check("parse_numstat counts the file", summary["files_changed"] == 1, repr(summary))
    check("parse_numstat surfaces the decoded blocklist path",
          paths == [DECODED] and paths[0].startswith("auth/"), repr(paths))

    print(f"\n{passed}/{passed + failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())

# tested-by: CONSILIUM-SCOPE-GATE-001
