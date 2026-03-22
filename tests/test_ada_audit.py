"""Tests for tools/ada-audit/audit.py."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PY = REPO_ROOT / "tools" / "ada-audit" / "audit.py"


@pytest.fixture(scope="module")
def ada():
    _mod_key = "ada_audit_test_module"
    spec = importlib.util.spec_from_file_location(_mod_key, AUDIT_PY)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {AUDIT_PY}")
    mod = importlib.util.module_from_spec(spec)
    prev = sys.modules.get(_mod_key)
    sys.modules[_mod_key] = mod
    spec.loader.exec_module(mod)
    yield mod
    if prev is None:
        sys.modules.pop(_mod_key, None)
    else:
        sys.modules[_mod_key] = prev


def _violations_by_rule(violations, rule):
    return [v for v in violations if v.rule == rule]


# ---------------------------------------------------------------------------
# img-alt rule
# ---------------------------------------------------------------------------


class TestImgAlt:
    def test_img_missing_alt_is_error(self, ada):
        html = "<html lang='en'><body><img src='foo.png'></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "img-alt")
        assert len(vs) == 1
        assert vs[0].severity == "error"

    def test_img_with_alt_passes(self, ada):
        html = "<html lang='en'><body><img src='foo.png' alt='A photo'></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "img-alt")
        assert vs == []

    def test_img_empty_alt_is_warning(self, ada):
        html = "<html lang='en'><body><img src='foo.png' alt=''></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "img-alt-empty")
        assert len(vs) == 1
        assert vs[0].severity == "warning"


# ---------------------------------------------------------------------------
# input-label rule
# ---------------------------------------------------------------------------


class TestInputLabel:
    def test_input_without_label_is_error(self, ada):
        html = "<html lang='en'><body><input type='text'></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "input-label")
        assert len(vs) == 1
        assert vs[0].severity == "error"

    def test_input_with_for_label_passes(self, ada):
        html = """<html lang='en'><body>
            <label for='name'>Name</label>
            <input type='text' id='name'>
        </body></html>"""
        vs = _violations_by_rule(ada.audit_html(html), "input-label")
        assert vs == []

    def test_input_with_aria_label_passes(self, ada):
        html = "<html lang='en'><body><input type='text' aria-label='Name'></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "input-label")
        assert vs == []

    def test_hidden_input_skipped(self, ada):
        html = "<html lang='en'><body><input type='hidden' name='csrf'></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "input-label")
        assert vs == []

    def test_submit_button_skipped(self, ada):
        html = "<html lang='en'><body><input type='submit' value='Send'></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "input-label")
        assert vs == []

    def test_textarea_without_label_is_error(self, ada):
        html = "<html lang='en'><body><textarea></textarea></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "input-label")
        assert len(vs) == 1

    def test_implicit_label_wrapping_passes(self, ada):
        """<label><input></label> — implicit label association must be accepted."""
        html = "<html lang='en'><body><label>Name <input type='text'></label></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "input-label")
        assert vs == []


# ---------------------------------------------------------------------------
# heading-empty rule
# ---------------------------------------------------------------------------


class TestHeadingEmpty:
    def test_empty_h1_is_error(self, ada):
        html = "<html lang='en'><body><h1></h1></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "heading-empty")
        assert len(vs) == 1
        assert vs[0].severity == "error"

    def test_whitespace_only_heading_is_error(self, ada):
        html = "<html lang='en'><body><h2>   </h2></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "heading-empty")
        assert len(vs) == 1

    def test_heading_with_text_passes(self, ada):
        html = "<html lang='en'><body><h1>Page Title</h1></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "heading-empty")
        assert vs == []

    def test_heading_with_nested_span_passes(self, ada):
        """<h1><span>Title</span></h1> must not trigger heading-empty."""
        html = "<html lang='en'><body><h1><span>Section Title</span></h1></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "heading-empty")
        assert vs == []


# ---------------------------------------------------------------------------
# document-lang rule
# ---------------------------------------------------------------------------


class TestDocumentLang:
    def test_missing_lang_is_error(self, ada):
        html = "<html><body><p>Hello</p></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "document-lang")
        assert len(vs) == 1
        assert vs[0].severity == "error"

    def test_empty_lang_is_error(self, ada):
        html = "<html lang=''><body><p>Hello</p></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "document-lang")
        assert len(vs) == 1

    def test_valid_lang_passes(self, ada):
        html = "<html lang='en'><body><p>Hello</p></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "document-lang")
        assert vs == []

    def test_lang_es_passes(self, ada):
        html = "<html lang='es'><body><p>Hola</p></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "document-lang")
        assert vs == []


# ---------------------------------------------------------------------------
# link-text rule
# ---------------------------------------------------------------------------


class TestLinkText:
    def test_empty_link_is_error(self, ada):
        html = "<html lang='en'><body><a href='/page'></a></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "link-text-empty")
        assert len(vs) == 1

    def test_vague_link_is_warning(self, ada):
        html = "<html lang='en'><body><a href='/page'>click here</a></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "link-text-vague")
        assert len(vs) == 1
        assert vs[0].severity == "warning"

    def test_descriptive_link_passes(self, ada):
        html = "<html lang='en'><body><a href='/page'>View bill summary</a></body></html>"
        vs = [v for v in ada.audit_html(html) if v.rule.startswith("link-text")]
        assert vs == []

    def test_aria_label_overrides_empty_text(self, ada):
        html = "<html lang='en'><body><a href='/page' aria-label='Go to about page'></a></body></html>"
        vs = [v for v in ada.audit_html(html) if v.rule.startswith("link-text")]
        assert vs == []

    def test_nested_span_provides_text(self, ada):
        """<a><span>Text</span></a> should not trigger link-text-empty."""
        html = "<html lang='en'><body><a href='/page'><span>View bill</span></a></body></html>"
        vs = [v for v in ada.audit_html(html) if v.rule.startswith("link-text")]
        assert vs == []

    def test_title_attr_passes(self, ada):
        """Link with title attribute must not trigger link-text-empty."""
        html = "<html lang='en'><body><a href='/page' title='Home'></a></body></html>"
        vs = [v for v in ada.audit_html(html) if v.rule.startswith("link-text")]
        assert vs == []

    def test_img_alt_inside_link_passes(self, ada):
        """Icon-only link <a><img alt='Home'></a> must not trigger link-text-empty."""
        html = "<html lang='en'><body><a href='/'><img src='home.svg' alt='Home'></a></body></html>"
        vs = [v for v in ada.audit_html(html) if v.rule.startswith("link-text")]
        assert vs == []


# ---------------------------------------------------------------------------
# button-text rule
# ---------------------------------------------------------------------------


class TestButtonText:
    def test_empty_button_is_error(self, ada):
        html = "<html lang='en'><body><button></button></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "button-text")
        assert len(vs) == 1

    def test_button_with_text_passes(self, ada):
        html = "<html lang='en'><body><button>Submit</button></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "button-text")
        assert vs == []

    def test_button_with_aria_label_passes(self, ada):
        html = "<html lang='en'><body><button aria-label='Close dialog'></button></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "button-text")
        assert vs == []

    def test_button_with_nested_span_passes(self, ada):
        """<button><span>Text</span></button> must not trigger button-text."""
        html = "<html lang='en'><body><button><span>Submit form</span></button></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "button-text")
        assert vs == []

    def test_button_title_passes(self, ada):
        """Button with title attribute must not trigger button-text."""
        html = "<html lang='en'><body><button title='Close'></button></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "button-text")
        assert vs == []

    def test_img_alt_inside_button_passes(self, ada):
        """Icon-only button <button><img alt='Close'></button> must not trigger button-text."""
        html = "<html lang='en'><body><button><img src='x.svg' alt='Close'></button></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "button-text")
        assert vs == []


# ---------------------------------------------------------------------------
# table-headers rule
# ---------------------------------------------------------------------------


class TestTableHeaders:
    def test_table_without_th_is_warning(self, ada):
        html = "<html lang='en'><body><table><tr><td>Cell</td></tr></table></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "table-headers")
        assert len(vs) == 1
        assert vs[0].severity == "warning"

    def test_table_with_th_passes(self, ada):
        html = "<html lang='en'><body><table><tr><th>Header</th><td>Cell</td></tr></table></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "table-headers")
        assert vs == []

    def test_no_table_no_violation(self, ada):
        html = "<html lang='en'><body><p>No table here</p></body></html>"
        vs = _violations_by_rule(ada.audit_html(html), "table-headers")
        assert vs == []

    def test_nested_table_outer_without_th_is_warning(self, ada):
        """Outer table with no <th> should warn even when inner table has <th>."""
        html = (
            "<html lang='en'><body>"
            "<table><tr><td>"
            "<table><tr><th>Inner header</th></tr></table>"
            "</td></tr></table>"
            "</body></html>"
        )
        vs = _violations_by_rule(ada.audit_html(html), "table-headers")
        # The outer table has no direct <th> — must still warn.
        assert len(vs) == 1

    def test_nested_table_both_with_th_pass(self, ada):
        """Both outer and inner tables with <th> should produce no violations."""
        html = (
            "<html lang='en'><body>"
            "<table><tr><th>Outer header</th><td>"
            "<table><tr><th>Inner header</th></tr></table>"
            "</td></tr></table>"
            "</body></html>"
        )
        vs = _violations_by_rule(ada.audit_html(html), "table-headers")
        assert vs == []


# ---------------------------------------------------------------------------
# audit_html / audit_file integration
# ---------------------------------------------------------------------------


class TestAuditHtml:
    def test_clean_html_no_violations(self, ada):
        html = """<!DOCTYPE html>
        <html lang="en">
        <head><title>Test</title></head>
        <body>
            <h1>Main Title</h1>
            <img src="photo.jpg" alt="A landscape photo">
            <label for="name">Your name</label>
            <input type="text" id="name">
            <a href="/about">About us</a>
            <button>Submit</button>
        </body>
        </html>"""
        violations = ada.audit_html(html)
        assert violations == []

    def test_violations_sorted_by_line(self, ada):
        html = """<html>
        <body>
        <img src='a.png'>
        <img src='b.png'>
        </body>
        </html>"""
        violations = ada.audit_html(html)
        lines = [v.line for v in violations if v.line is not None]
        assert lines == sorted(lines)


class TestAuditFile:
    def test_reads_and_audits_file(self, ada, tmp_path):
        path = tmp_path / "page.html"
        path.write_text("<html><body><img src='x.jpg'></body></html>", encoding="utf-8")
        violations = ada.audit_file(path)
        assert any(v.rule == "img-alt" for v in violations)

    def test_unreadable_file_returns_violation_not_exception(self, ada, tmp_path):
        path = tmp_path / "nonexistent.html"
        violations = ada.audit_file(path)
        assert len(violations) == 1
        assert violations[0].rule == "file-read-error"
        assert violations[0].severity == "error"

    def test_non_utf8_file_returns_violation_not_exception(self, ada, tmp_path):
        """A Latin-1/corrupt file must produce file-read-error, not raise UnicodeDecodeError."""
        path = tmp_path / "latin1.html"
        path.write_bytes(b"\xff\xfe<html><body>Caf\xe9</body></html>")
        violations = ada.audit_file(path)
        assert len(violations) == 1
        assert violations[0].rule == "file-read-error"


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class TestFormatText:
    def test_no_violations_message(self, ada, tmp_path):
        path = tmp_path / "ok.html"
        text = ada.format_text(path, [])
        assert "no violations" in text

    def test_violation_appears_in_output(self, ada, tmp_path):
        path = tmp_path / "page.html"
        v = ada.Violation(
            rule="img-alt", severity="error", message="Missing alt",
            element="<img>", line=5,
        )
        text = ada.format_text(path, [v])
        assert "img-alt" in text
        assert "ERROR" in text


class TestFormatJson:
    def test_json_structure(self, ada, tmp_path):
        path = tmp_path / "page.html"
        v = ada.Violation(
            rule="img-alt", severity="error", message="Missing alt",
            element="<img>", line=5,
        )
        result = ada.format_json(path, [v])
        assert result["violation_count"] == 1
        assert result["violations"][0]["rule"] == "img-alt"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_default_fail_on_is_errors(self, ada):
        parser = ada._build_parser()
        args = parser.parse_args(["page.html"])
        assert args.fail_on == "errors"

    def test_format_json(self, ada):
        parser = ada._build_parser()
        args = parser.parse_args(["page.html", "--format", "json"])
        assert args.output_format == "json"

    def test_fail_on_violations(self, ada):
        parser = ada._build_parser()
        args = parser.parse_args(["page.html", "--fail-on", "violations"])
        assert args.fail_on == "violations"

    def test_main_clean_file_exits_zero(self, ada, tmp_path):
        html = '<html lang="en"><body><p>Hello</p></body></html>'
        path = tmp_path / "clean.html"
        path.write_text(html, encoding="utf-8")
        assert ada.main([str(path)]) == 0

    def test_main_error_violation_exits_nonzero(self, ada, tmp_path):
        html = "<html lang='en'><body><img src='x.png'></body></html>"
        path = tmp_path / "bad.html"
        path.write_text(html, encoding="utf-8")
        assert ada.main([str(path)]) == 1

    def test_main_fail_on_violations_exits_nonzero_on_warning(self, ada, tmp_path):
        html = "<html lang='en'><body><img src='x.png' alt=''></body></html>"
        path = tmp_path / "warn.html"
        path.write_text(html, encoding="utf-8")
        assert ada.main([str(path), "--fail-on", "violations"]) == 1
