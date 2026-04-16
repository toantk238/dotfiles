# Design: Improved `audit_deprecated_apis.py`

**Date:** 2026-04-13
**Status:** Approved

## Goal

A one-shot audit script that scans an Android Kotlin codebase for all `@Deprecated` interfaces, classes, and methods in service-layer files, finds every usage across the codebase, and writes results to a CSV — one row per usage — for handoff to the team.

## Approach

Improve `audit_deprecated_apis.py` in place (Option A). It is the stronger of the two existing scripts. Fix its two known bugs, extend declaration detection to cover classes, and delete the weaker `audit_deprecated_services.py`.

## Changes

### 1. Fix `extract_parens_content` — string-aware paren counting

**Problem:** The current implementation counts `(` and `)` naively, miscounting when they appear inside string literals (e.g., `@Deprecated("Use foo(bar) instead")`).

**Fix:** Track an `in_string` boolean that flips on each unescaped `"`. Only adjust paren depth when `in_string` is `False`.

```python
def extract_parens_content(text: str, start: int) -> Tuple[str, int]:
    assert text[start] == "("
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
```

### 2. Fix `find_next_declaration` — proper annotation skip

**Problem:** The current 600-char slice + `"@Deprecated" not in pre` check is fragile for multi-line annotations or closely spaced deprecated items.

**Fix:** After consuming the annotation's closing `)`, advance through whitespace and any additional `@Annotation` lines using a small forward loop, then match the declaration at the resulting position.

```python
def find_next_declaration(text: str, pos: int) -> Optional[Tuple[str, str]]:
    # Skip whitespace and additional @Annotation lines
    while pos < len(text):
        # skip whitespace
        while pos < len(text) and text[pos] in ' \t\n\r':
            pos += 1
        if pos < len(text) and text[pos] == '@':
            # skip this annotation line
            end = text.find('\n', pos)
            pos = end + 1 if end != -1 else len(text)
        else:
            break

    chunk = text[pos:]
    decl = re.match(
        r'(?:(?:abstract|open|data|sealed)\s+)*'
        r'(?:suspend\s+)?'
        r'(?P<kind>interface|class|fun)\s+(?P<name>\w+)',
        chunk,
    )
    if not decl:
        return None
    raw_kind = decl.group('kind')
    kind = 'method' if raw_kind == 'fun' else raw_kind  # 'interface' or 'class'
    return kind, decl.group('name')
```

### 3. Extend `DeprecatedItem.kind` to include `"class"`

`kind` now holds one of `"interface"`, `"class"`, or `"method"`.

### 4. Extend `find_usages` to handle `"class"`

Classes are used as types just like interfaces, so apply the same word-boundary pattern and tag them as `injection`.

```python
if item.kind in ("interface", "class"):
    pattern = re.compile(r'\b' + re.escape(item.name) + r'\b')
    usage_type = "injection"
else:  # method
    pattern = re.compile(r'\.' + re.escape(item.name) + r'\s*[<(]')
    usage_type = "call_site"
```

### 5. Delete `audit_deprecated_services.py`

Superseded by the improved script. Remove from the repo.

### 6. Extend `test_audit_deprecated_apis.py`

Add test cases for:
- Annotation with parens inside a string literal (paren parser fix)
- `abstract class`, `open class`, `data class` declarations (class detection)
- Two `@Deprecated` items declared back-to-back (declaration finder fix)

## Output

CSV at `<project_root>/deprecated_api_audit.csv`, one row per usage:

| Column | Description |
|---|---|
| `deprecated_item` | Name of the deprecated symbol |
| `type` | `interface`, `class`, or `method` |
| `deprecation_message` | Message from the annotation |
| `replacement_hint` | From `ReplaceWith` or message text |
| `file` | Declaring file (relative to project root) |
| `module` | Derived Gradle module label |
| `usage_file` | File containing the usage |
| `usage_line` | Line number of the usage |
| `usage_type` | `injection` or `call_site` |

Items with no usages emit one row with empty `usage_file`, `usage_line`, `usage_type`.

## Files Touched

| File | Action |
|---|---|
| `scripts/audit_deprecated_apis.py` | Modified |
| `scripts/audit_deprecated_services.py` | Deleted |
| `scripts/test_audit_deprecated_apis.py` | Extended |
