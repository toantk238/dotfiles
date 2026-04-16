#!/usr/bin/env python3
"""Unit tests for audit_deprecated_apis.py — stdlib unittest, no extra deps."""

import contextlib
import sys
import tempfile
import unittest
from pathlib import Path

# Script lives in the same directory as this test file
sys.path.insert(0, str(Path(__file__).parent))

# These imports will fail until the script exists — that is expected at this step
from audit_deprecated_apis import (
    derive_module,
    extract_parens_content,
    parse_annotation,
    find_next_declaration,
    extract_deprecated_items,
)
import audit_deprecated_apis as _mod


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestDeriveModule(unittest.TestCase):

    def test_manadr_api_library(self):
        path = PROJECT_ROOT / "libraries/manadr_api/library/src/main/kotlin/Foo.kt"
        self.assertEqual(derive_module(path), "manadr_api/library")

    def test_cms_api(self):
        path = PROJECT_ROOT / "libraries/manadr_api/cms-api/src/main/kotlin/Foo.kt"
        self.assertEqual(derive_module(path), "manadr_api/cms-api")

    def test_app(self):
        path = PROJECT_ROOT / "app/src/main/java/Foo.kt"
        self.assertEqual(derive_module(path), "app")

    def test_internal(self):
        path = PROJECT_ROOT / "internal/business/src/main/kotlin/Foo.kt"
        self.assertEqual(derive_module(path), "internal/business")


class TestExtractParensContent(unittest.TestCase):

    def test_simple(self):
        text = 'foo("bar") rest'
        content, end = extract_parens_content(text, 3)
        self.assertEqual(content, '"bar"')
        self.assertEqual(text[end:], " rest")

    def test_nested_parens(self):
        text = '(outer (inner) end) after'
        content, end = extract_parens_content(text, 0)
        self.assertEqual(content, "outer (inner) end")
        self.assertEqual(text[end:], " after")

    def test_unmatched_paren_inside_string(self):
        # Naive depth counting breaks when '(' appears unmatched inside a string
        text = '@Deprecated("Open paren ( here") rest'
        content, end = extract_parens_content(text, 11)
        self.assertEqual(content, '"Open paren ( here"')
        self.assertEqual(text[end:], ' rest')


class TestParseAnnotation(unittest.TestCase):

    def test_empty_message_no_hint(self):
        msg, hint = parse_annotation('""')
        self.assertEqual(msg, "")
        self.assertEqual(hint, "")

    def test_migrate_to_hint(self):
        msg, hint = parse_annotation('"Migrate to TeleConsultKsxService.createRefMemo"')
        self.assertEqual(msg, "Migrate to TeleConsultKsxService.createRefMemo")
        self.assertEqual(hint, "TeleConsultKsxService.createRefMemo")

    def test_use_hint(self):
        _, hint = parse_annotation('"Use CommunicationService.createVideoCall"')
        self.assertEqual(hint, "CommunicationService.createVideoCall")

    def test_replace_with_overrides_message_hint(self):
        body = '"Old message", replaceWith = ReplaceWith("WFService", imports = [])'
        msg, hint = parse_annotation(body)
        self.assertEqual(msg, "Old message")
        self.assertEqual(hint, "WFService")

    def test_multiline_replace_with(self):
        body = '\n    "",\n    replaceWith = ReplaceWith(\n        "WFService",\n        "com.example"\n    )'
        _, hint = parse_annotation(body)
        self.assertEqual(hint, "WFService")

    def test_no_hint_in_non_empty_message(self):
        msg, hint = parse_annotation('"Removed"')
        self.assertEqual(msg, "Removed")
        self.assertEqual(hint, "")


class TestFindNextDeclaration(unittest.TestCase):

    def test_finds_interface(self):
        text = '\ninterface TeleConsultService {'
        result = find_next_declaration(text, 0)
        self.assertEqual(result, ("interface", "TeleConsultService"))

    def test_finds_suspend_fun(self):
        text = '\n@POST("foo")\nsuspend fun createRefMemo('
        result = find_next_declaration(text, 0)
        self.assertEqual(result, ("method", "createRefMemo"))

    def test_finds_plain_fun(self):
        text = '\nfun getPatientConsults('
        result = find_next_declaration(text, 0)
        self.assertEqual(result, ("method", "getPatientConsults"))

    def test_stops_at_nested_deprecated(self):
        # A @Deprecated immediately before fun skipMe means skipMe is attributed
        # to that nested @Deprecated, not the outer one. So the result from pos=0
        # must be None (no un-guarded declaration follows).
        text = '\n@Deprecated("")\nfun skipMe('
        result = find_next_declaration(text, 0)
        self.assertIsNone(result)

    def test_returns_none_for_empty(self):
        result = find_next_declaration("   ", 0)
        self.assertIsNone(result)


class TestExtractDeprecatedItems(unittest.TestCase):
    """Tests that write temp Kotlin files and call extract_deprecated_items."""

    def _patch_root(self, tmp_path: Path):
        """Context manager: temporarily redirect PROJECT_ROOT to tmp_path."""
        @contextlib.contextmanager
        def _ctx():
            original = _mod.PROJECT_ROOT
            _mod.PROJECT_ROOT = tmp_path
            try:
                yield
            finally:
                _mod.PROJECT_ROOT = original

        return _ctx()

    def _make_kt(self, tmp_path: Path, content: str) -> Path:
        kt = tmp_path / "service" / "TestService.kt"
        kt.parent.mkdir(parents=True, exist_ok=True)
        kt.write_text(content, encoding="utf-8")
        return kt

    def test_interface_level_deprecated(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kt = self._make_kt(tmp_path, '@Deprecated("")\ninterface TestService {\n}\n')
            with self._patch_root(tmp_path):
                items = extract_deprecated_items(kt)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].name, "TestService")
            self.assertEqual(items[0].kind, "interface")
            self.assertEqual(items[0].message, "")
            self.assertEqual(items[0].module, "service")

    def test_method_level_deprecated_with_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kt = self._make_kt(
                tmp_path,
                'interface TestService {\n'
                '    @Deprecated("use bar")\n'
                '    suspend fun foo(): Unit\n'
                '}\n',
            )
            with self._patch_root(tmp_path):
                items = extract_deprecated_items(kt)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].name, "foo")
            self.assertEqual(items[0].kind, "method")
            self.assertEqual(items[0].replacement_hint, "bar")

    def test_multiline_annotation_with_replace_with(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kt = self._make_kt(
                tmp_path,
                '@Deprecated(\n'
                '    "",\n'
                '    replaceWith = ReplaceWith("WFService")\n'
                ')\n'
                'interface WorkFlowService {\n}\n',
            )
            with self._patch_root(tmp_path):
                items = extract_deprecated_items(kt)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].name, "WorkFlowService")
            self.assertEqual(items[0].replacement_hint, "WFService")

    def test_commented_out_deprecated_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kt = self._make_kt(
                tmp_path,
                'interface TestService {\n'
                '//    @Deprecated("remove")\n'
                '//    fun oldMethod(): Unit\n'
                '    fun active(): Unit\n'
                '}\n',
            )
            with self._patch_root(tmp_path):
                items = extract_deprecated_items(kt)
            self.assertEqual(len(items), 0)

    def test_both_interface_and_method_deprecated(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            kt = self._make_kt(
                tmp_path,
                '@Deprecated("")\n'
                'interface TestService {\n'
                '    @Deprecated("use newMethod")\n'
                '    fun oldMethod(): Unit\n'
                '}\n',
            )
            with self._patch_root(tmp_path):
                items = extract_deprecated_items(kt)
            kinds = {i.kind for i in items}
            names = {i.name for i in items}
            self.assertIn("interface", kinds)
            self.assertIn("method", kinds)
            self.assertIn("TestService", names)
            self.assertIn("oldMethod", names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
