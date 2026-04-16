#!/usr/bin/env python3
"""
Scans manadr_api library modules for @Deprecated service interfaces/classes,
finds all usages across the codebase, and writes results to deprecated_api_audit.csv.

Usage: python3 scripts/audit_deprecated_services.py
Run from the project root directory.
"""

import re
import csv
import sys
from pathlib import Path
from typing import List, Tuple

# Directories to scan for deprecated service definitions
SCAN_DIRS = [
    "libraries/manadr_api/library",
    "libraries/manadr_api/cms-api",
    "libraries/manadr_api/api-next",
]

# Directories to search for usages
USAGE_SEARCH_DIRS = [
    "app",
    "libraries",
]

# Directories/patterns to skip during usage search
SKIP_DIRS = {"build", ".gradle", ".git", "generated"}

OUTPUT_CSV = "deprecated_api_audit.csv"

# Regex to extract first string argument from @Deprecated("...") or @Deprecated(\n    "...",...)
first_string_re = re.compile(r'@Deprecated\s*\(\s*"([^"]*)"')

# Regex to match interface/class declaration
decl_re = re.compile(
    r'(?:interface|(?:(?:abstract|open)\s+)?class)\s+(\w+)'
)

# Regex to skip annotations and whitespace before declaration
skip_re = re.compile(r'^[\s]*(?:@\S+[^\n]*\n[\s]*)*')


def find_deprecated_services(root: Path) -> List[Tuple[str, str, str]]:
    """
    Walk SCAN_DIRS and find all @Deprecated interface/class declarations.

    Returns list of (service_name, deprecation_message, relative_file_path).
    """
    results = []

    for scan_dir in SCAN_DIRS:
        scan_path = root / scan_dir
        if not scan_path.exists():
            print(f"  [SKIP] Directory not found: {scan_dir}", file=sys.stderr)
            continue

        for kt_file in scan_path.rglob("*.kt"):
            # Skip build and generated directories
            if any(part in SKIP_DIRS for part in kt_file.parts):
                continue
            found = extract_deprecated_declarations(kt_file, root)
            results.extend(found)

    return results


def extract_deprecated_declarations(
    kt_file: Path, root: Path
) -> List[Tuple[str, str, str]]:
    """
    Parse a single .kt file and return all (name, message, rel_path) tuples
    where the interface or class is preceded by @Deprecated.
    Handles both single-line @Deprecated("msg") and multi-arg @Deprecated(...) blocks.
    """
    text = kt_file.read_text(encoding="utf-8")
    rel_path = str(kt_file.relative_to(root))

    # Find every @Deprecated annotation start position
    deprecated_starts = [m.start() for m in re.finditer(r'@Deprecated', text)]

    found = []
    for start in deprecated_starts:
        # Extract deprecation message (best effort from first string arg)
        msg_match = first_string_re.match(text, start)
        message = msg_match.group(1) if msg_match else ""

        # Skip past the annotation block: find the position after its closing paren
        # (or just after "@Deprecated" if there are no parens)
        pos = start + len("@Deprecated")
        # Skip whitespace
        while pos < len(text) and text[pos] in (' ', '\t', '\n', '\r'):
            pos += 1

        if pos < len(text) and text[pos] == '(':
            # Consume the full parenthesised block, counting nesting
            # Track whether we're inside a string literal to avoid counting parens in strings
            depth = 0
            in_string = False
            while pos < len(text):
                ch = text[pos]
                if ch == '"' and (pos == 0 or text[pos - 1] != '\\'):
                    in_string = not in_string
                if not in_string:
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        depth -= 1
                        if depth == 0:
                            pos += 1
                            break
                pos += 1
        # pos is now just after the closing ')' (or at the next char if no parens)

        # Skip remaining annotations and whitespace to reach the declaration
        # Allow: blank lines, other @Annotation lines, until we hit non-@ non-blank
        remaining = text[pos:]
        # Strip leading whitespace and any other @Annotation lines
        skip_m = skip_re.match(remaining)
        if skip_m:
            remaining = remaining[skip_m.end():]

        # Now check for interface/class declaration
        decl_m = decl_re.match(remaining)
        if decl_m:
            name = decl_m.group(1)
            found.append((name, message, rel_path))

    return found


def find_usages(service_name: str, root: Path) -> List[str]:
    """
    Search all .kt files under USAGE_SEARCH_DIRS for references to service_name.

    Returns list of "relative/path/to/File.kt:lineno" strings.
    """
    # Matches the service name used as a Kotlin type:
    #   ": IamService" / "IamService," / "IamService)" / "IamService " / "IamService\n"
    pattern = re.compile(r'\b' + re.escape(service_name) + r'\b')

    matches = []
    for search_dir in USAGE_SEARCH_DIRS:
        search_path = root / search_dir
        if not search_path.exists():
            continue

        for kt_file in search_path.rglob("*.kt"):
            # Skip build and generated directories
            if any(part in SKIP_DIRS for part in kt_file.parts):
                continue

            try:
                lines = kt_file.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            rel = str(kt_file.relative_to(root))
            for lineno, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches.append(f"{rel}:{lineno}")

    return matches


def write_csv(rows: list, output_path: Path) -> None:
    """Write audit results to CSV."""
    fieldnames = [
        "service_name",
        "deprecation_message",
        "service_file",
        "usage_count",
        "usage_locations",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    root = Path(__file__).parent.parent.resolve()
    print(f"Project root: {root}")

    print("\n=== Phase 1: Discovering deprecated service declarations ===")
    services = find_deprecated_services(root)
    if not services:
        print("No deprecated service interfaces found.")
        sys.exit(0)
    for name, msg, path in services:
        print(f"  Found: {name!r}  message={msg!r}  in {path}")
    print(f"\nTotal: {len(services)} deprecated service(s) found.")

    print("\n=== Phase 2: Searching for usages ===")
    rows = []  # rows is consumed by Phase 3 (write_csv)
    for service_name, deprecation_message, service_file in services:
        usages = find_usages(service_name, root)
        usage_locations = "; ".join(usages)
        rows.append({
            "service_name": service_name,
            "deprecation_message": deprecation_message,
            "service_file": service_file,
            "usage_count": len(usages),
            "usage_locations": usage_locations,
        })
        print(f"  {service_name}: {len(usages)} usage(s)")
        for loc in usages:
            print(f"    {loc}")

    print("\n=== Phase 3: Writing CSV ===")
    output_path = root / OUTPUT_CSV
    try:
        write_csv(rows, output_path)
        print(f"CSV written to: {output_path}")
        print(f"Rows: {len(rows)}")
    except OSError as e:
        print(f"[ERROR] Could not write CSV: {e}", file=sys.stderr)
        sys.exit(1)
