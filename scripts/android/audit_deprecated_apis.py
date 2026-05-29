#!/usr/bin/env python3
"""Audit deprecated API services and their usages across the Android codebase.

Usage:
    python3 scripts/audit_deprecated_apis.py
Output:
    deprecated_api_audit.csv in the project root
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVICE_DIR_KEYWORDS = ["/service/", "/remote/", "/api/"]


@dataclass
class DeprecatedItem:
    name: str
    kind: str            # "interface" or "method"
    message: str
    replacement_hint: str
    file: str            # relative to PROJECT_ROOT
    module: str


@dataclass
class Usage:
    file: str            # relative to PROJECT_ROOT
    line: int
    usage_type: str      # "injection" or "call_site"


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_service_file(path: Path) -> bool:
    s = path.as_posix()
    return any(kw in s for kw in SERVICE_DIR_KEYWORDS)


def derive_module(path: Path) -> str:
    """Derive a short Gradle module label from a file path."""
    parts = path.relative_to(PROJECT_ROOT).parts
    if parts[0] == "libraries" and len(parts) > 2:
        return f"{parts[1]}/{parts[2]}"
    if parts[0] == "internal" and len(parts) > 1:
        return f"internal/{parts[1]}"
    return parts[0]


def extract_parens_content(text: str, start: int) -> Tuple[str, int]:
    """Return (content, end_pos) for balanced parens starting at index `start`.

    `start` must point to the opening '(' character.
    `end_pos` is the index of the first character *after* the closing ')'.
    String literals are tracked so that parens inside strings are ignored.
    """
    assert text[start] == "(", f"Expected '(' at position {start}, got {text[start]!r}"
    depth = 0
    in_string = False
    i = start
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
        if not in_string:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return text[start + 1 : i], i + 1
        i += 1
    return text[start + 1 :], len(text)


def parse_annotation(ann_body: str) -> Tuple[str, str]:
    """Parse the body of a @Deprecated(...) annotation.

    Returns (message, replacement_hint).

    Priority for replacement_hint:
      1. `replaceWith = ReplaceWith("SomeClass.method", ...)` — most explicit
      2. Message text matching "Migrate to X" / "Use X" / "use X"
      3. Empty string
    """
    msg_match = re.search(r'"([^"]*)"', ann_body)
    message = msg_match.group(1) if msg_match else ""

    rw_match = re.search(r'ReplaceWith\s*\(\s*"([^"]+)"', ann_body)
    if rw_match:
        hint = rw_match.group(1)
    else:
        hint_match = re.search(
            r'(?:Migrate to|migrate to|Use|use)\s+([\w.]+)', message
        )
        hint = hint_match.group(1) if hint_match else ""

    return message, hint


def find_next_declaration(text: str, pos: int) -> Optional[Tuple[str, str]]:
    """Find the nearest interface or fun name after position `pos`.

    Searches up to 600 characters ahead. Returns None if another @Deprecated
    appears before a candidate (meaning the candidate belongs to a different
    @Deprecated), or if nothing is found.

    Returns ("interface"|"method", name) on success.
    """
    chunk = text[pos : pos + 600]

    candidates: List[Tuple[int, str, str]] = []

    iface = re.search(r'\binterface\s+(\w+)', chunk)
    if iface:
        pre = chunk[: iface.start()]
        if "@Deprecated" not in pre:
            candidates.append((iface.start(), "interface", iface.group(1)))

    func = re.search(r'(?:suspend\s+)?fun\s+(\w+)\s*[<(]', chunk)
    if func:
        pre = chunk[: func.start()]
        if "@Deprecated" not in pre:
            candidates.append((func.start(), "method", func.group(1)))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2]


# ── Core logic ────────────────────────────────────────────────────────────────

def extract_deprecated_items(path: Path) -> List[DeprecatedItem]:
    """Extract all @Deprecated interfaces and methods from a Kotlin service file."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    rel = str(path.relative_to(PROJECT_ROOT))
    module = derive_module(path)
    items: List[DeprecatedItem] = []

    for m in re.finditer(r'@Deprecated\s*\(', text):
        # Skip commented-out @Deprecated (line starts with //)
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_prefix = text[line_start : m.start()].strip()
        if line_prefix.startswith("//") or line_prefix.startswith("*"):
            continue

        # The '(' is the last char matched by the regex; step back one
        paren_pos = m.end() - 1
        ann_body, end_pos = extract_parens_content(text, paren_pos)
        message, hint = parse_annotation(ann_body)

        declaration = find_next_declaration(text, end_pos)
        if declaration is None:
            continue
        kind, name = declaration

        items.append(DeprecatedItem(
            name=name, kind=kind, message=message,
            replacement_hint=hint, file=rel, module=module,
        ))

    return items


def find_usages(item: DeprecatedItem, all_kt: List[Path]) -> List[Usage]:
    """Search all .kt files for references to `item`, excluding its declaring file."""
    declaring = str(PROJECT_ROOT / item.file)

    if item.kind == "interface":
        pattern = re.compile(r'\b' + re.escape(item.name) + r'\b')
        usage_type = "injection"
    else:
        pattern = re.compile(r'\.' + re.escape(item.name) + r'\s*[<(]')
        usage_type = "call_site"

    usages: List[Usage] = []
    for kt in all_kt:
        if str(kt) == declaring:
            continue
        try:
            lines = kt.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        rel = str(kt.relative_to(PROJECT_ROOT))
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                usages.append(Usage(file=rel, line=i, usage_type=usage_type))

    return usages


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    all_kt = list(PROJECT_ROOT.rglob("*.kt"))
    service_files = [f for f in all_kt if is_service_file(f)]

    print(f"Scanning {len(service_files)} service files across {len(all_kt)} total .kt files …")

    items: List[DeprecatedItem] = []
    for sf in service_files:
        items.extend(extract_deprecated_items(sf))

    print(f"Found {len(items)} deprecated items\n")

    output = PROJECT_ROOT / "deprecated_api_audit.csv"
    fieldnames = [
        "deprecated_item", "type", "deprecation_message", "replacement_hint",
        "file", "module", "usage_file", "usage_line", "usage_type",
    ]

    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            usages = find_usages(item, all_kt)
            print(f"  {item.name} ({item.kind}): {len(usages)} usage(s)")
            if not usages:
                writer.writerow({
                    "deprecated_item": item.name,
                    "type": item.kind,
                    "deprecation_message": item.message,
                    "replacement_hint": item.replacement_hint,
                    "file": item.file,
                    "module": item.module,
                    "usage_file": "",
                    "usage_line": "",
                    "usage_type": "",
                })
            else:
                for u in usages:
                    writer.writerow({
                        "deprecated_item": item.name,
                        "type": item.kind,
                        "deprecation_message": item.message,
                        "replacement_hint": item.replacement_hint,
                        "file": item.file,
                        "module": item.module,
                        "usage_file": u.file,
                        "usage_line": u.line,
                        "usage_type": u.usage_type,
                    })

    print(f"\nCSV written → {output}")
    with open(output, encoding="utf-8", newline="") as fh:
        total_usages = sum(1 for row in csv.DictReader(fh) if row["usage_file"])
    print(f"Rows with usages: {total_usages} | Items with no usages: {len(items) - total_usages}")


if __name__ == "__main__":
    main()
