---
milestone: v1.2
id: CONSILIUM-CHECK-PUBLIC-LEAK-001
status: confirmed
level: code
layer: feature
owner: alxmax
depends_on: []
risk: 1
satisfies: [ARCH-CONSILIUM-REPO-GATES-001]
---

# check_public_leak

> Fails CI if any git-tracked file references the private repo or a local developer path.

## Description

Every line in this section is binding.

- `check_public_leak.py` scans all files tracked by `git ls-files` in the current working directory; it takes no CLI flags and runs unconditionally.
- `check_public_leak.py` guards the public release repository against accidentally referencing the private development repository, or leaking local developer paths.
- `check_public_leak.py` scans every git-tracked text file for two compiled regex patterns: a reference to the private dev repo (the owner/name slug, excluding the public `_Demo` mirror), and an absolute local path under the author's working tree.
- The exact patterns live in the source; this doc deliberately does not quote them, because doing so would itself trip the guard.
- Binary and image file extensions are skipped.
- The guard file itself is excluded from its own scan.
- The check is wired into CI and fails with exit 1, printing the offending `file:line: description: match` tuples to stderr, making private-repo references un-shippable rather than a silent leak.
- `check_public_leak.py` prints `public-leak guard: clean` to stdout on success.
- On failure, it prints `file:line: description` strings to stderr.
- `check_public_leak.py` exits 0 on clean, and 1 on any pattern match.
- The `PATTERNS` constant and its inline comments are the sole specification for the regex patterns; there is no secondary config or spec file.
- The skip list (`SKIP_SUFFIX`) is a heuristic hardcoded tuple of 11 extensions; a binary file committed with a `.txt` extension is not skipped — it is read with `errors="ignore"` and scanned like any text file.
- When run outside a git repository (`git ls-files` fails), the script raises an unhandled `subprocess.CalledProcessError` and exits 1 with a Python traceback to stderr — the same exit code as a leak find, but distinguishable by the traceback.

## Verify intent

- None - all questions resolved.

## Cases

- **CASE-1** — Given a repo with no private-repo (non-Demo) or local-path references, when `check_public_leak.py` runs, then it exits 0 and prints `clean`.
- **CASE-2** — Given a tracked file containing a non-Demo private-repo reference, when `check_public_leak.py` runs, then it exits 1 with the file and line number printed to stderr.
- **CASE-3** — Given a tracked file containing an absolute local developer path, when `check_public_leak.py` runs, then it exits 1 with the offending location reported.
- **CASE-4** — Given binary and image files (`.png`, `.woff`) that match the patterns byte-for-byte, when `check_public_leak.py` runs, then those files are skipped.
- **CASE-5** — Given the guard script itself (`check_public_leak.py`), when it scans the repo, then it excludes itself from the scan and never self-reports.

## Context (non-binding)

**Current implementation** — `scripts/check_public_leak.py`.
