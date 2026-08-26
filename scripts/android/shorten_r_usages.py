#!/usr/bin/env python3
"""
Shorten fully-qualified R references in Kotlin sources after enabling nonTransitiveRClass.

Rewrites   com.mhealth.chat.R.string.foo
into       chatR.string.foo
and adds   import com.mhealth.chat.R as chatR

The alias is the last package segment before `R`, camelCased, with `R` appended.
Only .kt files are touched (never .java).

Usage:
    python3 scripts/shorten_r_usages.py                 # dry run over the repo
    python3 scripts/shorten_r_usages.py --apply         # rewrite files
    python3 scripts/shorten_r_usages.py --apply app libraries
    python3 scripts/shorten_r_usages.py --packages      # just list the R packages found
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EXCLUDED_DIRS = {"build", ".git", ".gradle", ".idea", "generated", ".agent-context"}

# Resource types that may follow `.R.`. Restricting to this set keeps the
# matcher from firing on unrelated member chains that happen to contain `.R.`.
RES_TYPES = (
    "anim animator array attr bool color dimen drawable font fraction id integer "
    "interpolator layout menu mipmap navigation plurals raw string style styleable "
    "transition xml"
).split()

# Packages never aliased: `android.R.string.ok` is already as short as it gets,
# and `androidR` would only add noise.
SKIP_PACKAGES = {"android"}

RES_TYPE_ALT = "|".join(RES_TYPES)
R_REF_RE = re.compile(
    r"(?<![\w.`$])"                                   # not mid-identifier / mid-chain
    r"(?P<pkg>[a-z][A-Za-z0-9_]*(?:\.[a-z][A-Za-z0-9_]*)+)"  # lowercase dotted package
    r"\.R\."
    r"(?=(?:" + RES_TYPE_ALT + r")\b)"                # followed by a resource type
)

IMPORT_RE = re.compile(r"^\s*import\s+([\w.`]+)(?:\s+as\s+(\w+))?\s*$")
PACKAGE_RE = re.compile(r"^\s*package\s+[\w.`]+\s*$")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ---------------------------------------------------------------------------
# Kotlin lexing: which offsets are real code (not comment / string literal)?
# ---------------------------------------------------------------------------


def code_mask(src: str) -> bytearray:
    """Return a mask where mask[i] is 1 when src[i] is executable code.

    Comments, char literals and string bodies are masked out, but the code
    inside a `${...}` string template is masked back in -- the repo really does
    contain `"res:///${com.mhealth.core.R.drawable.ic_avatar}"`.
    """
    mask = bytearray(len(src))
    # stack entries: ("code", brace_depth) | ("str", raw: bool) | ("line") | ("block", depth) | ("char")
    stack = [["code", 0]]
    i = 0
    n = len(src)
    while i < n:
        top = stack[-1]
        kind = top[0]

        if kind == "code":
            c = src[i]
            two = src[i : i + 2]
            if two == "//":
                stack.append(["line"])
                i += 2
                continue
            if two == "/*":
                stack.append(["block", 1])
                i += 2
                continue
            if src.startswith('"""', i):
                stack.append(["str", True])
                i += 3
                continue
            if c == '"':
                stack.append(["str", False])
                i += 1
                continue
            if c == "'":
                stack.append(["char"])
                i += 1
                continue
            if c == "`":  # backtick-quoted identifier
                j = src.find("`", i + 1)
                j = n if j == -1 else j + 1
                for k in range(i, j):
                    mask[k] = 1
                i = j
                continue
            if c == "{":
                top[1] += 1
            elif c == "}":
                if top[1] == 0 and len(stack) > 1:
                    # closes a `${` template hole -> back to the enclosing string
                    stack.pop()
                    i += 1
                    continue
                top[1] -= 1
            mask[i] = 1
            i += 1
            continue

        if kind == "line":
            j = src.find("\n", i)
            i = n if j == -1 else j
            stack.pop()
            continue

        if kind == "block":
            two = src[i : i + 2]
            if two == "/*":
                top[1] += 1
                i += 2
                continue
            if two == "*/":
                top[1] -= 1
                i += 2
                if top[1] == 0:
                    stack.pop()
                continue
            i += 1
            continue

        if kind == "char":
            if src[i] == "\\":
                i += 2
                continue
            if src[i] == "'":
                stack.pop()
            i += 1
            continue

        # kind == "str"
        raw = top[1]
        if not raw and src[i] == "\\":
            i += 2
            continue
        if src.startswith("${", i):
            stack.append(["code", 0])
            i += 2
            continue
        if raw:
            if src.startswith('"""', i):
                stack.pop()
                i += 3
                continue
        elif src[i] == '"' or src[i] == "\n":
            stack.pop()
            i += 1
            continue
        i += 1

    return mask


# ---------------------------------------------------------------------------
# Alias naming
# ---------------------------------------------------------------------------


def camel(segments: list[str]) -> str:
    """['compose', 'views'] -> 'composeViews'; ['jetpack_compose_common'] -> 'jetpackComposeCommon'."""
    words: list[str] = []
    for seg in segments:
        words.extend(w for w in seg.split("_") if w)
    if not words:
        return "res"
    head, *tail = words
    return head[0].lower() + head[1:] + "".join(w[0].upper() + w[1:] for w in tail)


def alias_candidates(pkg: str) -> list[str]:
    """Shortest-first alias candidates: coreR, mhealthCoreR, comMhealthCoreR."""
    segs = pkg.split(".")
    return [camel(segs[-depth:]) + "R" for depth in range(1, len(segs) + 1)]


def resolve_aliases(pkgs: list[str], taken: set[str], priority: dict[str, int]) -> dict[str, str]:
    """Assign each package the shortest alias that collides with nothing in the file.

    On a clash the repo-wide more common package keeps the short alias, so e.g.
    com.mhealth.core stays `coreR` everywhere and com.manadr.ai.core becomes
    `aiCoreR` -- rather than the winner depending on alphabetical luck.
    """
    order = sorted(pkgs, key=lambda p: (-priority.get(p, 0), p))
    depth = {p: 1 for p in pkgs}
    chosen: dict[str, str] = {}
    for _ in range(8):
        chosen = {p: alias_candidates(p)[min(depth[p], len(alias_candidates(p))) - 1] for p in pkgs}
        clashed = False
        seen: dict[str, str] = {}
        for p in order:
            a = chosen[p]
            if a in taken or (a in seen and seen[a] != p):
                if depth[p] < len(p.split(".")):
                    depth[p] += 1
                    clashed = True
                    continue
            seen[a] = p
        if not clashed:
            return chosen
    return chosen


# ---------------------------------------------------------------------------
# Per-file rewrite
# ---------------------------------------------------------------------------


class FileResult:
    def __init__(self, path: Path):
        self.path = path
        self.aliases: dict[str, str] = {}
        self.reused: dict[str, str] = {}
        self.replacements = 0
        self.new_text: str | None = None
        self.skipped: list[str] = []


def process(path: Path, text: str, priority: dict[str, int] | None = None) -> FileResult:
    res = FileResult(path)
    mask = code_mask(text)

    lines = text.splitlines(keepends=True)
    line_start = []
    off = 0
    for ln in lines:
        line_start.append(off)
        off += len(ln)

    # Existing imports: reuse a hand-written alias when one already exists.
    existing_alias: dict[str, str] = {}
    plain_imports: set[str] = set()
    import_lines: list[int] = []
    package_line = -1
    for idx, ln in enumerate(lines):
        if PACKAGE_RE.match(ln) and package_line == -1:
            package_line = idx
        m = IMPORT_RE.match(ln)
        if m:
            import_lines.append(idx)
            fq, alias = m.group(1), m.group(2)
            if fq.endswith(".R"):
                pkg = fq[:-2]
                if alias:
                    existing_alias[pkg] = alias
                else:
                    plain_imports.add(pkg)

    import_span = range(import_lines[0], import_lines[-1] + 1) if import_lines else range(0)
    import_offsets = {
        (line_start[i], line_start[i] + len(lines[i])) for i in import_span if IMPORT_RE.match(lines[i])
    }

    def in_import(pos: int) -> bool:
        return any(a <= pos < b for a, b in import_offsets)

    matches = []
    for m in R_REF_RE.finditer(text):
        s, e = m.span()
        if not all(mask[i] for i in range(s, e)):
            continue
        if in_import(s):
            continue
        pkg = m.group("pkg")
        if pkg in SKIP_PACKAGES or "." not in pkg:
            res.skipped.append(pkg)
            continue
        matches.append((s, e, pkg))

    if not matches:
        return res

    pkgs = sorted({p for _, _, p in matches})
    need_alias = [p for p in pkgs if p not in existing_alias]

    # Identifiers already used in this file must not be shadowed by a new alias.
    taken = set(existing_alias.values())
    taken |= {i for i in IDENT_RE.findall(text) if i.endswith("R")}

    assigned = resolve_aliases(need_alias, taken, priority or {})
    alias_of = dict(existing_alias)
    alias_of.update(assigned)

    res.aliases = {p: alias_of[p] for p in need_alias}
    res.reused = {p: existing_alias[p] for p in pkgs if p in existing_alias}
    res.replacements = len(matches)

    # Rewrite right-to-left so earlier offsets stay valid.
    out = text
    for s, e, pkg in sorted(matches, reverse=True):
        out = out[:s] + alias_of[pkg] + "." + out[e:]

    new_imports = [f"import {p}.R as {alias_of[p]}\n" for p in sorted(need_alias)]
    if new_imports:
        out = insert_imports(out, new_imports)

    res.new_text = out
    return res


def insert_imports(text: str, new_imports: list[str]) -> str:
    lines = text.splitlines(keepends=True)
    idxs = [i for i, ln in enumerate(lines) if IMPORT_RE.match(ln)]

    if not idxs:
        pkg_idx = next((i for i, ln in enumerate(lines) if PACKAGE_RE.match(ln)), -1)
        at = pkg_idx + 1 if pkg_idx >= 0 else 0
        block = list(new_imports)
        if at < len(lines) and lines[at].strip():
            block.append("\n")
        if at > 0 and lines[at - 1].strip():
            block.insert(0, "\n")
        return "".join(lines[:at] + block + lines[at:])

    first, last = idxs[0], idxs[-1]
    block = [lines[i] for i in idxs]
    was_sorted = block == sorted(block, key=import_sort_key)

    merged = block + [n for n in new_imports if n not in block]
    if was_sorted:
        merged = sorted(merged, key=import_sort_key)
    # Rebuild the region, dropping the old import lines but keeping anything
    # interleaved (blank lines, comments) that sat between them.
    region = []
    for i in range(first, last + 1):
        if i not in idxs:
            region.append(lines[i])
    return "".join(lines[:first] + merged + region + lines[last + 1 :])


def import_sort_key(line: str):
    m = IMPORT_RE.match(line)
    return (m.group(1), m.group(2) or "") if m else (line, "")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def kotlin_files(roots: list[Path]):
    for root in roots:
        if root.is_file():
            if root.suffix == ".kt":
                yield root
            continue
        for p in root.rglob("*.kt"):
            if any(part in EXCLUDED_DIRS for part in p.parts):
                continue
            yield p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="*", default=["."], help="files or directories to scan (default: .)")
    ap.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    ap.add_argument("--packages", action="store_true", help="only list the R packages found, with their alias")
    ap.add_argument("-v", "--verbose", action="store_true", help="print every file that changes")
    args = ap.parse_args()

    roots = [Path(r).resolve() for r in (args.roots or ["."])]
    files = sorted(kotlin_files(roots))

    # Pass 1 -- repo-wide usage counts, so alias collisions resolve the same
    # way in every file instead of per-file alphabetical order.
    priority: dict[str, int] = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if ".R." not in text:
            continue
        for m in R_REF_RE.finditer(text):
            pkg = m.group("pkg")
            priority[pkg] = priority.get(pkg, 0) + 1

    pkg_counts: dict[str, int] = {}
    changed: list[FileResult] = []
    total_repl = 0
    skipped: dict[str, int] = {}

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            print(f"!! skip {path}: {exc}", file=sys.stderr)
            continue
        if ".R." not in text:
            continue
        res = process(path, text, priority)
        for p in res.skipped:
            skipped[p] = skipped.get(p, 0) + 1
        if not res.replacements:
            continue
        for p in list(res.aliases) + list(res.reused):
            pkg_counts[p] = pkg_counts.get(p, 0) + 1
        total_repl += res.replacements
        changed.append(res)
        if args.apply and res.new_text is not None and not args.packages:
            path.write_text(res.new_text, encoding="utf-8")
        if args.verbose and not args.packages:
            names = ", ".join(f"{p.split('.')[-1]}->{a}" for p, a in sorted(res.aliases.items()))
            reuse = ", ".join(f"{p.split('.')[-1]}->{a}(existing)" for p, a in sorted(res.reused.items()))
            detail = " | ".join(x for x in (names, reuse) if x)
            print(f"{res.replacements:3d}  {rel(path)}  [{detail}]")

    if args.packages:
        print(f"{'count':>6}  {'alias':<26} package")
        for p, c in sorted(pkg_counts.items(), key=lambda kv: -kv[1]):
            print(f"{c:>6}  {alias_candidates(p)[0]:<26} {p}")
        if skipped:
            print("\nnot aliased (single-segment / skip list):")
            for p, c in sorted(skipped.items(), key=lambda kv: -kv[1]):
                print(f"{c:>6}  {p}")
        return 0

    mode = "rewrote" if args.apply else "would rewrite"
    print(f"\n{mode} {total_repl} reference(s) across {len(changed)} file(s) of {len(files)} scanned")
    if skipped:
        print("left alone: " + ", ".join(f"{p} ({c})" for p, c in sorted(skipped.items(), key=lambda kv: -kv[1])))
    if not args.apply and changed:
        print("re-run with --apply to write the changes")
    return 0


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(Path.cwd()))
    except ValueError:
        return str(p)


if __name__ == "__main__":
    raise SystemExit(main())
