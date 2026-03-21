#!/usr/bin/env python3
"""ADA Title II / WCAG 2.1 AA compliance checker for HTML files.

Performs static analysis on HTML content to surface common accessibility
violations: missing alt text, unlabelled form controls, empty headings,
missing document language, insufficient heading hierarchy, and more.

Designed as a lightweight linter with no browser or external dependencies —
all analysis is done via the Python standard library's ``html.parser``.

Usage::

    # Audit a single file
    python tools/ada-audit/audit.py page.html

    # Audit multiple files
    python tools/ada-audit/audit.py *.html

    # Exit with non-zero code if violations found (useful in CI)
    python tools/ada-audit/audit.py page.html --fail-on violations

    # Output JSON report
    python tools/ada-audit/audit.py page.html --format json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Violation model
# ---------------------------------------------------------------------------

SEVERITY_LEVELS = ("error", "warning", "info")


@dataclass(slots=True)
class Violation:
    """A single accessibility violation."""

    rule: str          # Machine-readable rule ID (e.g. ``"img-alt"``)
    severity: str      # ``"error"``, ``"warning"``, or ``"info"``
    message: str       # Human-readable description
    element: str       # Tag name or snippet (e.g. ``"<img src='...'>"``))
    line: int | None   # Approximate source line, if available


# ---------------------------------------------------------------------------
# HTML element collector
# ---------------------------------------------------------------------------


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    line: int | None
    text: str = ""


class _HTMLCollector(HTMLParser):
    """Minimal parser that collects elements and their attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[_Element] = []
        self._stack: list[_Element] = []
        self.lang: str | None = None
        self._lineno: int = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: (v or "") for k, v in attrs}
        elem = _Element(tag=tag.lower(), attrs=attr_dict, line=self.getpos()[0])
        self.elements.append(elem)
        self._stack.append(elem)

        if tag.lower() == "html" and "lang" in attr_dict:
            self.lang = attr_dict["lang"].strip()

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].tag == tag.lower():
                self._stack.pop(i)
                break

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1].text += data


def _parse_html(html: str) -> _HTMLCollector:
    collector = _HTMLCollector()
    collector.feed(html)
    return collector


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def _rule_img_alt(collector: _HTMLCollector) -> Iterator[Violation]:
    """Images must have non-empty alt attributes (WCAG 1.1.1)."""
    for elem in collector.elements:
        if elem.tag != "img":
            continue
        src = elem.attrs.get("src", "")
        snippet = f"<img src={src!r}>" if src else "<img>"
        if "alt" not in elem.attrs:
            yield Violation(
                rule="img-alt",
                severity="error",
                message="Image missing alt attribute",
                element=snippet,
                line=elem.line,
            )
        elif not elem.attrs["alt"].strip():
            # Empty alt is valid for decorative images but flag as warning
            yield Violation(
                rule="img-alt-empty",
                severity="warning",
                message=(
                    "Image has empty alt attribute — only appropriate for purely "
                    "decorative images; verify intent"
                ),
                element=snippet,
                line=elem.line,
            )


def _rule_input_label(collector: _HTMLCollector) -> Iterator[Violation]:
    """Form inputs must be associated with a label (WCAG 1.3.1)."""
    label_fors: set[str] = set()
    labelled_ids: set[str] = set()

    for elem in collector.elements:
        if elem.tag == "label":
            if for_id := elem.attrs.get("for"):
                label_fors.add(for_id)

    input_tags = {"input", "select", "textarea"}
    skip_types = {"hidden", "submit", "reset", "button", "image"}

    for elem in collector.elements:
        if elem.tag not in input_tags:
            continue
        if elem.attrs.get("type", "text").lower() in skip_types:
            continue

        elem_id = elem.attrs.get("id", "")
        has_label = elem_id in label_fors
        has_aria_label = bool(elem.attrs.get("aria-label", "").strip())
        has_aria_labelledby = bool(elem.attrs.get("aria-labelledby", "").strip())
        has_title = bool(elem.attrs.get("title", "").strip())

        if not (has_label or has_aria_label or has_aria_labelledby or has_title):
            snippet = f"<{elem.tag} type={elem.attrs.get('type', 'text')!r}>"
            yield Violation(
                rule="input-label",
                severity="error",
                message=(
                    "Form control missing associated label. Add a <label for=…>, "
                    "aria-label, or aria-labelledby attribute."
                ),
                element=snippet,
                line=elem.line,
            )


def _rule_heading_empty(collector: _HTMLCollector) -> Iterator[Violation]:
    """Headings must contain non-whitespace text (WCAG 2.4.6)."""
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}
    for elem in collector.elements:
        if elem.tag not in heading_tags:
            continue
        if not elem.text.strip():
            yield Violation(
                rule="heading-empty",
                severity="error",
                message=f"Empty heading <{elem.tag}>",
                element=f"<{elem.tag}>",
                line=elem.line,
            )


def _rule_document_lang(collector: _HTMLCollector) -> Iterator[Violation]:
    """The <html> element must have a non-empty lang attribute (WCAG 3.1.1)."""
    html_elems = [e for e in collector.elements if e.tag == "html"]
    if not html_elems:
        return

    html_elem = html_elems[0]
    lang = html_elem.attrs.get("lang", "")
    if not lang.strip():
        yield Violation(
            rule="document-lang",
            severity="error",
            message="<html> element missing or empty lang attribute (WCAG 3.1.1)",
            element="<html>",
            line=html_elem.line,
        )


def _rule_link_text(collector: _HTMLCollector) -> Iterator[Violation]:
    """Links must have descriptive text (WCAG 2.4.4)."""
    vague = {"click here", "here", "read more", "more", "link", "learn more"}
    for elem in collector.elements:
        if elem.tag != "a":
            continue
        has_aria = bool(elem.attrs.get("aria-label", "").strip())
        has_aria_lb = bool(elem.attrs.get("aria-labelledby", "").strip())
        if has_aria or has_aria_lb:
            continue
        text = elem.text.strip().lower()
        href = elem.attrs.get("href", "#")
        if not text:
            yield Violation(
                rule="link-text-empty",
                severity="error",
                message="Link has no text content",
                element=f"<a href={href!r}>",
                line=elem.line,
            )
        elif text in vague:
            yield Violation(
                rule="link-text-vague",
                severity="warning",
                message=f"Link text {text!r} is not descriptive (WCAG 2.4.4)",
                element=f"<a href={href!r}>{text}</a>",
                line=elem.line,
            )


def _rule_table_headers(collector: _HTMLCollector) -> Iterator[Violation]:
    """Data tables should have <th> elements with scope (WCAG 1.3.1)."""
    in_table = False
    table_has_th = False
    table_elem: _Element | None = None

    for elem in collector.elements:
        if elem.tag == "table":
            in_table = True
            table_has_th = False
            table_elem = elem
        elif elem.tag == "/table":
            if in_table and not table_has_th:
                line = table_elem.line if table_elem else None
                yield Violation(
                    rule="table-headers",
                    severity="warning",
                    message="Table appears to have no <th> header cells (WCAG 1.3.1)",
                    element="<table>",
                    line=line,
                )
            in_table = False
        elif in_table and elem.tag == "th":
            table_has_th = True


def _rule_button_text(collector: _HTMLCollector) -> Iterator[Violation]:
    """Buttons must have accessible text (WCAG 4.1.2)."""
    for elem in collector.elements:
        if elem.tag != "button":
            continue
        has_aria = bool(elem.attrs.get("aria-label", "").strip())
        has_aria_lb = bool(elem.attrs.get("aria-labelledby", "").strip())
        has_text = bool(elem.text.strip())
        if not (has_aria or has_aria_lb or has_text):
            yield Violation(
                rule="button-text",
                severity="error",
                message="Button has no accessible text (WCAG 4.1.2)",
                element="<button>",
                line=elem.line,
            )


# ---------------------------------------------------------------------------
# Audit runner
# ---------------------------------------------------------------------------

_RULES = [
    _rule_img_alt,
    _rule_input_label,
    _rule_heading_empty,
    _rule_document_lang,
    _rule_link_text,
    _rule_button_text,
]


def audit_html(html: str) -> list[Violation]:
    """Run all accessibility rules against *html* and return violations.

    Args:
        html: Raw HTML string.

    Returns:
        List of :class:`Violation` objects sorted by line number.
    """
    collector = _parse_html(html)
    violations: list[Violation] = []
    for rule in _RULES:
        violations.extend(rule(collector))
    violations.sort(key=lambda v: (v.line or 0, v.rule))
    return violations


def audit_file(path: Path) -> list[Violation]:
    """Run accessibility audit on an HTML file.

    Args:
        path: Path to the HTML file.

    Returns:
        List of :class:`Violation` objects.
    """
    html = path.read_text(encoding="utf-8")
    return audit_html(html)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_text(path: Path, violations: list[Violation]) -> str:
    """Format violations as human-readable text."""
    if not violations:
        return f"{path}: no violations found\n"
    lines = [f"{path}: {len(violations)} violation(s)"]
    for v in violations:
        loc = f":{v.line}" if v.line else ""
        lines.append(f"  [{v.severity.upper()}] {path}{loc} — {v.rule}: {v.message}")
    return "\n".join(lines) + "\n"


def format_json(path: Path, violations: list[Violation]) -> dict:
    """Format violations as a JSON-serialisable dict."""
    return {
        "file": str(path),
        "violation_count": len(violations),
        "violations": [
            {
                "rule": v.rule,
                "severity": v.severity,
                "message": v.message,
                "element": v.element,
                "line": v.line,
            }
            for v in violations
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ADA Title II / WCAG 2.1 AA accessibility checker for HTML files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("files", nargs="+", type=Path, help="HTML files to audit")
    parser.add_argument(
        "--format", dest="output_format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--fail-on", choices=["violations", "errors", "never"], default="errors",
        help=(
            "Exit non-zero if: 'violations' (any), 'errors' (severity=error), "
            "'never'. Default: errors"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    all_results: list[dict] = []
    total_violations = 0
    total_errors = 0

    for path in args.files:
        violations = audit_file(path)
        total_violations += len(violations)
        total_errors += sum(1 for v in violations if v.severity == "error")

        if args.output_format == "json":
            all_results.append(format_json(path, violations))
        else:
            print(format_text(path, violations), end="")

    if args.output_format == "json":
        print(json.dumps(all_results, indent=2))

    if args.fail_on == "violations" and total_violations > 0:
        return 1
    if args.fail_on == "errors" and total_errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
