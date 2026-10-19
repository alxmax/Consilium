"""The open questions a code draft asks: one per signal the scan can point at."""
import ast, re

# A draft used to ask every file the same thing ("anything that looks like an
# accident ... intended, or a bug to fix?"), so `_findings.md` held N copies
# of one sentence and named nothing. Each question below names the line it
# is about. The scan reads; only the author knows whether the shape is meant.
DRAFT_QUESTION_MAX = 8
# A marker counts only inside a comment: the word in a string literal is data,
# and `TODO.md` is a file name.
_MARKER_RE = re.compile(
    r"(?:#|//|/\*|<!--|--|^\s*\*)[^\n]*?\b(TODO|FIXME|HACK|XXX)\b(?!\.\w)")
_SUPPRESS_RE = re.compile(
    r"#\s*noqa\b|#\s*type:\s*ignore\b|pylint:\s*disable|eslint-disable"
    r"|@ts-(?:ignore|expect-error)\b|\bNOLINT\b")
_EMPTY_CATCH_RE = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}")
# Numbers too common to mean anything on their own.
_PLAIN_NUMBERS = frozenset((0, 1, 2, -1))
_EXIT = (ast.Return, ast.Raise, ast.Continue, ast.Break)

_ASK = {
    "marker": "left in the code. Part of the contract, or out of scope?",
    "suppress": "silences a check. Intended, or a bug the check found?",
    "swallow": "swallows the error. Intended fail-open, or a bug to fix?",
    "magic": "is an unnamed number. What does it stand for, and in what "
             "unit?",
    "dead": "can never run: it follows a return/raise. Delete it, or is "
            "the exit the bug?",
}


def _snippet(line):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    s = " ".join(line.strip().replace("`", "'").split())
    return s if len(s) <= 60 else s[:57] + "..."


def _swallows(handler):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """True when an except body only passes, continues or returns nothing."""
    for st in handler.body:
        if isinstance(st, (ast.Pass, ast.Continue)):
            continue
        if isinstance(st, ast.Return) and (
                st.value is None or (isinstance(st.value, ast.Constant)
                                     and st.value.value is None)):
            continue
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue                     # a docstring-like string or `...`
        return False
    return True


def _magic(node):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """The number a comparison or a keyword argument hard-codes, else None."""
    vals = []
    if isinstance(node, ast.Compare):
        vals = [node.left] + list(node.comparators)
    elif isinstance(node, ast.keyword):
        vals = [node.value]
    for v in vals:
        if isinstance(v, ast.UnaryOp) and isinstance(v.op, ast.USub):
            v = v.operand
        if (isinstance(v, ast.Constant) and type(v.value) in (int, float)
                and v.value not in _PLAIN_NUMBERS):
            return v
    return None


def _py_signals(src):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """(line, kind) for every swallowed error, magic number inside a
    function, and statement after an unconditional exit. An unparseable
    file has none: the regex signals still apply."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return []
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.ExceptHandler) and _swallows(node):
                out.append((node.lineno, "swallow"))
            v = _magic(node)
            if v is not None:
                out.append((v.lineno, "magic"))
            for body in (getattr(node, f, None)
                         for f in ("body", "orelse", "finalbody")):
                if not isinstance(body, list):
                    continue
                for a, b in zip(body, body[1:]):
                    if isinstance(a, _EXIT) and isinstance(b, ast.stmt):
                        out.append((b.lineno, "dead"))
                        break
    return out


def draft_questions(rel, src):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """The Verify-intent bullets for one code draft, ordered by line, at
    most DRAFT_QUESTION_MAX of them, and the number left out. Each bullet
    reads `Observed at `rel:N`: `code` <question>`. Empty when the scan
    finds nothing: the caller then keeps the generic question."""
    lines = src.splitlines()
    found = []
    for n, line in enumerate(lines, 1):
        if _MARKER_RE.search(line):
            found.append((n, "marker"))
        elif _SUPPRESS_RE.search(line):
            found.append((n, "suppress"))
        if _EMPTY_CATCH_RE.search(line):
            found.append((n, "swallow"))
    if rel.endswith(".py"):
        found += _py_signals(src)
    seen, items = set(), []
    for n, kind in sorted(set(found)):
        if n in seen or not 0 < n <= len(lines):
            continue                     # one question per line is enough
        seen.add(n)
        items.append("Observed at `{}:{}`: `{}` {}".format(
            rel, n, _snippet(lines[n - 1]), _ASK[kind]))
    return items[:DRAFT_QUESTION_MAX], max(0, len(items) - DRAFT_QUESTION_MAX)


def verify_section(rel, src):
    # implements: ARCH-EXTRACT-008  # implements: REQ-EXTRACT-1099
    """(the Verify-intent bullets, a Context note on what the cap left out)
    for one code draft. A file with no signal keeps the generic question."""
    asks, more = draft_questions(rel, src)
    text = "".join("- {}\n".format(q) for q in asks) or (
        "- TODO: anything that looks like an accident (swallowed error, "
        "magic constant, dead branch) — intended, or a bug to fix?\n")
    note = "\n{} more signal(s) past the first {} — read the file.\n".format(
        more, DRAFT_QUESTION_MAX) if more else ""
    return text, note
