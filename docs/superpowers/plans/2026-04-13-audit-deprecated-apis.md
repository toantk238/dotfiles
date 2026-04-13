# Improved audit_deprecated_apis.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two parser bugs in `audit_deprecated_apis.py`, extend it to detect deprecated classes, and delete the superseded `audit_deprecated_services.py`.

**Architecture:** Three targeted fixes to existing functions (`extract_parens_content`, `find_next_declaration`, `find_usages`), each preceded by a failing test. TDD throughout. One commit per task.

**Tech Stack:** Python 3, stdlib only (`re`, `csv`, `pathlib`, `dataclasses`, `unittest`)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/audit_deprecated_apis.py` | Modify | Main script — parser, declaration finder, usage search |
| `scripts/test_audit_deprecated_apis.py` | Modify | Unit tests — extend with new cases per task |
| `scripts/audit_deprecated_services.py` | Delete | Superseded script — removed in Task 4 |

---

## Task 1: Fix `extract_parens_content` — string-aware paren counting

**Files:**
- Modify: `scripts/test_audit_deprecated_apis.py` — add to `TestExtractParensContent`
- Modify: `scripts/audit_deprecated_apis.py:54-69`

The current implementation counts `(` and `)` naively. An unmatched `(` inside a string literal (e.g., `@Deprecated("Open paren ( here")`) causes the depth counter to overshoot, returning the wrong content and end position.

- [ ] **Step 1: Add the failing test**

In `scripts/test_audit_deprecated_apis.py`, inside `class TestExtractParensContent`, add after `test_nested_parens`:

```python
def test_unmatched_paren_inside_string(self):
    # Naive depth counting breaks when '(' appears unmatched inside a string
    text = '@Deprecated("Open paren ( here") rest'
    content, end = extract_parens_content(text, 11)
    self.assertEqual(content, '"Open paren ( here"')
    self.assertEqual(text[end:], ' rest')
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/scripts
python3 -m pytest test_audit_deprecated_apis.py::TestExtractParensContent::test_unmatched_paren_inside_string -v
```

Expected: **FAIL** — the naive parser reads past the closing `)` and returns the wrong slice.

- [ ] **Step 3: Fix `extract_parens_content` in `scripts/audit_deprecated_apis.py`**

Replace lines 54–69 (the entire `extract_parens_content` function) with:

```python
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
```

- [ ] **Step 4: Run all `TestExtractParensContent` tests and verify they pass**

```bash
python3 -m pytest test_audit_deprecated_apis.py::TestExtractParensContent -v
```

Expected: **3 PASSED** (`test_simple`, `test_nested_parens`, `test_unmatched_paren_inside_string`).

- [ ] **Step 5: Run the full test suite and verify no regressions**

```bash
python3 -m pytest test_audit_deprecated_apis.py -v
```

Expected: all previously passing tests still **PASS**.

- [ ] **Step 6: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add scripts/audit_deprecated_apis.py scripts/test_audit_deprecated_apis.py
git commit -m "fix: make extract_parens_content string-aware"
```

---

## Task 2: Rewrite `find_next_declaration` — annotation skip + class support

**Files:**
- Modify: `scripts/test_audit_deprecated_apis.py` — add to `TestFindNextDeclaration` and `TestExtractDeprecatedItems`
- Modify: `scripts/audit_deprecated_apis.py:97-125`

The current implementation uses a raw 600-char lookahead slice and checks for `@Deprecated` in the prefix. It misses `abstract class`, `open class`, `data class`, and `sealed class` declarations, and fails when two deprecated items appear back-to-back at file scope.

- [ ] **Step 1: Add failing tests for class detection**

In `scripts/test_audit_deprecated_apis.py`, inside `class TestFindNextDeclaration`, add after `test_returns_none_for_empty`:

```python
def test_finds_abstract_class(self):
    text = '\nabstract class OldClient {'
    result = find_next_declaration(text, 0)
    self.assertEqual(result, ("class", "OldClient"))

def test_finds_open_class(self):
    text = '\nopen class LegacyRepo {'
    result = find_next_declaration(text, 0)
    self.assertEqual(result, ("class", "LegacyRepo"))

def test_finds_data_class(self):
    text = '\ndata class OldRequest('
    result = find_next_declaration(text, 0)
    self.assertEqual(result, ("class", "OldRequest"))

def test_finds_plain_class(self):
    text = '\nclass SimpleService {'
    result = find_next_declaration(text, 0)
    self.assertEqual(result, ("class", "SimpleService"))
```

- [ ] **Step 2: Add failing test for back-to-back deprecated declarations**

In `scripts/test_audit_deprecated_apis.py`, inside `class TestExtractDeprecatedItems`, add after `test_both_interface_and_method_deprecated`:

```python
def test_back_to_back_deprecated_declarations(self):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        kt = self._make_kt(
            tmp_path,
            '@Deprecated("old interface")\n'
            'interface OldService\n'
            '@Deprecated("old class")\n'
            'abstract class OldImpl\n',
        )
        with self._patch_root(tmp_path):
            items = extract_deprecated_items(kt)
        self.assertEqual(len(items), 2)
        names = {i.name for i in items}
        self.assertIn("OldService", names)
        self.assertIn("OldImpl", names)
```

- [ ] **Step 3: Run the new tests and verify they fail**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/scripts
python3 -m pytest test_audit_deprecated_apis.py::TestFindNextDeclaration::test_finds_abstract_class test_audit_deprecated_apis.py::TestFindNextDeclaration::test_finds_open_class test_audit_deprecated_apis.py::TestFindNextDeclaration::test_finds_data_class test_audit_deprecated_apis.py::TestFindNextDeclaration::test_finds_plain_class test_audit_deprecated_apis.py::TestExtractDeprecatedItems::test_back_to_back_deprecated_declarations -v
```

Expected: **5 FAILED**.

- [ ] **Step 4: Rewrite `find_next_declaration` in `scripts/audit_deprecated_apis.py`**

Replace lines 97–125 (the entire `find_next_declaration` function) with:

```python
def find_next_declaration(text: str, pos: int) -> Optional[Tuple[str, str]]:
    """Find the nearest interface, class, or fun declaration after position `pos`.

    Skips whitespace and non-@Deprecated annotation lines. Returns None if
    another @Deprecated is encountered before a declaration (meaning the
    declaration belongs to that other @Deprecated), or if nothing is found.

    Returns ("interface"|"class"|"method", name) on success.
    """
    while pos < len(text):
        # skip whitespace
        while pos < len(text) and text[pos] in ' \t\n\r':
            pos += 1
        if pos >= len(text):
            return None
        if text[pos] == '@':
            # Another @Deprecated means this declaration is not ours
            if text[pos:].startswith('@Deprecated'):
                return None
            # Skip any other annotation line (e.g. @POST, @GET, @JvmStatic)
            eol = text.find('\n', pos)
            pos = eol + 1 if eol != -1 else len(text)
        else:
            break

    if pos >= len(text):
        return None

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
    kind = 'method' if raw_kind == 'fun' else raw_kind
    return kind, decl.group('name')
```

- [ ] **Step 5: Run all `TestFindNextDeclaration` and `TestExtractDeprecatedItems` tests**

```bash
python3 -m pytest test_audit_deprecated_apis.py::TestFindNextDeclaration test_audit_deprecated_apis.py::TestExtractDeprecatedItems -v
```

Expected: **all PASSED** (both existing and new tests).

- [ ] **Step 6: Run the full test suite and verify no regressions**

```bash
python3 -m pytest test_audit_deprecated_apis.py -v
```

Expected: all tests **PASS**.

- [ ] **Step 7: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add scripts/audit_deprecated_apis.py scripts/test_audit_deprecated_apis.py
git commit -m "feat: rewrite find_next_declaration to handle classes and annotation stacks"
```

---

## Task 3: Extend `find_usages` to handle `kind == "class"`

**Files:**
- Modify: `scripts/test_audit_deprecated_apis.py` — add `TestFindUsages` class
- Modify: `scripts/audit_deprecated_apis.py:162-186`
- Modify: `scripts/audit_deprecated_apis.py:14` — imports in test file

Currently `find_usages` falls through to the method branch (`else`) for `kind == "class"`, using a `.name(` pattern that never matches class-type usages.

- [ ] **Step 1: Extend the top-level import in `test_audit_deprecated_apis.py`**

Change the existing import block (lines 14–20) from:

```python
from audit_deprecated_apis import (
    derive_module,
    extract_parens_content,
    parse_annotation,
    find_next_declaration,
    extract_deprecated_items,
)
```

To:

```python
from audit_deprecated_apis import (
    DeprecatedItem,
    derive_module,
    extract_parens_content,
    parse_annotation,
    find_next_declaration,
    extract_deprecated_items,
    find_usages,
)
```

- [ ] **Step 2: Add the failing test**

In `scripts/test_audit_deprecated_apis.py`, add a new test class after `TestExtractDeprecatedItems`:

```python
class TestFindUsages(unittest.TestCase):

    def _patch_root(self, tmp_path: Path):
        @contextlib.contextmanager
        def _ctx():
            original = _mod.PROJECT_ROOT
            _mod.PROJECT_ROOT = tmp_path
            try:
                yield
            finally:
                _mod.PROJECT_ROOT = original
        return _ctx()

    def test_class_usage_tagged_as_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            declaring = tmp_path / "service" / "OldClient.kt"
            declaring.parent.mkdir(parents=True, exist_ok=True)
            declaring.write_text("abstract class OldClient\n", encoding="utf-8")
            usage_file = tmp_path / "app" / "Repo.kt"
            usage_file.parent.mkdir(parents=True, exist_ok=True)
            usage_file.write_text(
                "class Repo(val client: OldClient)\n", encoding="utf-8"
            )
            item = DeprecatedItem(
                name="OldClient",
                kind="class",
                message="",
                replacement_hint="",
                file=str(declaring.relative_to(tmp_path)),
                module="service",
            )
            with self._patch_root(tmp_path):
                usages = find_usages(item, [declaring, usage_file])
            self.assertEqual(len(usages), 1)
            self.assertEqual(usages[0].usage_type, "injection")
```

- [ ] **Step 3: Run the test and verify it fails**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/scripts
python3 -m pytest test_audit_deprecated_apis.py::TestFindUsages::test_class_usage_tagged_as_injection -v
```

Expected: **FAIL** — `usages` is empty because the method pattern (`.OldClient(`) doesn't match `OldClient` used as a type.

- [ ] **Step 4: Fix `find_usages` in `scripts/audit_deprecated_apis.py`**

In `find_usages` (around line 166), change:

```python
    if item.kind == "interface":
        pattern = re.compile(r'\b' + re.escape(item.name) + r'\b')
        usage_type = "injection"
    else:
        pattern = re.compile(r'\.' + re.escape(item.name) + r'\s*[<(]')
        usage_type = "call_site"
```

To:

```python
    if item.kind in ("interface", "class"):
        pattern = re.compile(r'\b' + re.escape(item.name) + r'\b')
        usage_type = "injection"
    else:
        pattern = re.compile(r'\.' + re.escape(item.name) + r'\s*[<(]')
        usage_type = "call_site"
```

- [ ] **Step 5: Run the full test suite**

```bash
python3 -m pytest test_audit_deprecated_apis.py -v
```

Expected: all tests **PASS**.

- [ ] **Step 6: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add scripts/audit_deprecated_apis.py scripts/test_audit_deprecated_apis.py
git commit -m "feat: tag deprecated class usages as injection"
```

---

## Task 4: Delete superseded script

**Files:**
- Delete: `scripts/audit_deprecated_services.py`

- [ ] **Step 1: Delete the file**

```bash
rm /mnt/Data/Workspace/2.Personal/dotfiles/scripts/audit_deprecated_services.py
```

- [ ] **Step 2: Run the full test suite to confirm nothing depended on it**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles/scripts
python3 -m pytest test_audit_deprecated_apis.py -v
```

Expected: all tests **PASS**.

- [ ] **Step 3: Commit**

```bash
cd /mnt/Data/Workspace/2.Personal/dotfiles
git add -u scripts/audit_deprecated_services.py
git commit -m "chore: remove superseded audit_deprecated_services.py"
```
