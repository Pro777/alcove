"""
Lightweight accessibility attribute tests for Alcove HTML templates.

These tests do not require a running browser or pytest-axe. They load the
Jinja2 templates and assert that required ARIA attributes, landmark roles,
and structural elements are present in the rendered HTML.

For full axe/WCAG coverage see the tracking issue:
https://github.com/Pro777/alcove-starter-private/issues/80
"""

import re
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "alcove" / "web" / "templates"
TEMPLATES_DIR = TEMPLATE_DIR  # alias used by new tests
STATIC_DIR = Path(__file__).resolve().parents[1] / "alcove" / "web" / "static"


def _read(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _read_path(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestBaseTemplate:
    def test_lang_en(self):
        html = _read("base.html")
        assert 'lang="en"' in html, "base.html must declare lang=\"en\" on <html>"

    def test_lang_attribute(self):
        html = _read("base.html")
        assert 'lang="en"' in html or "lang=" in html

    def test_skip_link_present(self):
        html = _read("base.html")
        assert 'href="#main-content"' in html, "skip link must target #main-content"
        assert "skip-link" in html
        assert "#main-content" in html
        # Skip link must appear before the main content block
        skip_pos = html.index('href="#main-content"')
        block_pos = html.index("{% block content %}")
        assert skip_pos < block_pos, "skip link must appear before {% block content %}"

    def test_skip_link_class(self):
        html = _read("base.html")
        assert 'class="skip-link"' in html, "skip link must carry .skip-link class"

    def test_theme_toggle_has_aria_label(self):
        html = _read("base.html")
        assert 'aria-label="Toggle theme"' in html

    def test_fouc_prevention_script(self):
        html = _read("base.html")
        head_match = re.search(r"<head>(.*?)</head>", html, re.DOTALL)
        assert head_match, "No <head> section found"
        head = head_match.group(1)
        assert "alcove-theme" in head, "FOUC prevention script missing from <head>"
        stylesheet_pos = head.find("style.css")
        script_pos = head.find("alcove-theme")
        assert script_pos < stylesheet_pos, "FOUC script must appear before stylesheet"

    def test_theme_toggle_three_states(self):
        html = _read("base.html")
        assert "'auto'" in html
        assert "'light'" in html
        assert "'dark'" in html


class TestSearchTemplate:
    def test_role_search(self):
        html = _read("search.html")
        assert 'role="search"' in html, "search form must have role=\"search\""

    def test_sr_only_label(self):
        html = _read("search.html")
        assert 'class="sr-only"' in html, "search label must be visually hidden with .sr-only"

    def test_upload_zone_role_button(self):
        html = _read("search.html")
        assert 'role="button"' in html, "upload zone must have role=\"button\""

    def test_upload_zone_tabindex(self):
        html = _read("search.html")
        assert 'tabindex="0"' in html, "upload zone must be keyboard-focusable via tabindex=\"0\""

    def test_upload_zone_aria_describedby_formats(self):
        html = _read("search.html")
        assert 'aria-describedby="formats-note"' in html, \
            "upload zone must reference formats-note via aria-describedby"
        assert 'id="formats-note"' in html, \
            "formats-note paragraph must carry id=\"formats-note\""

    def test_upload_status_aria_live_polite(self):
        html = _read("search.html")
        assert 'aria-live="polite"' in html, \
            "upload status must have aria-live=\"polite\""

    def test_upload_status_aria_atomic(self):
        html = _read("search.html")
        assert 'aria-atomic="true"' in html, \
            "upload status must have aria-atomic=\"true\""

    def test_upload_status_aria_busy_initial_false(self):
        html = _read("search.html")
        assert 'aria-busy="false"' in html, \
            "upload status must initialise with aria-busy=\"false\""

    def test_aria_busy_toggled_in_js(self):
        html = _read("search.html")
        assert 'aria-busy", "true"' in html or "aria-busy\", \"true\"" in html or \
               'setAttribute("aria-busy", "true")' in html, \
            "JS must set aria-busy=\"true\" when upload starts"
        assert 'setAttribute("aria-busy", "false")' in html, \
            "JS must set aria-busy=\"false\" when upload completes or fails"

    def test_aria_invalid_set_on_error(self):
        html = _read("search.html")
        assert 'setAttribute("aria-invalid", "true")' in html, \
            "JS must set aria-invalid=\"true\" on upload error"


class TestResultsTemplate:
    def test_results_region_role(self):
        html = _read("results.html")
        assert 'role="region"' in html, "results list must have role=\"region\""

    def test_results_region_aria_label(self):
        html = _read("results.html")
        assert 'aria-label="Search results"' in html, \
            "results region must be labelled \"Search results\""

    def test_results_region_aria_live_assertive(self):
        html = _read("results.html")
        assert 'aria-live="assertive"' in html, \
            "results region must have aria-live=\"assertive\" for immediate announcement"

    def test_result_cards_use_aria_describedby(self):
        html = _read("results.html")
        assert 'aria-describedby=' in html, \
            "result cards must use aria-describedby to reference metadata"
        assert "card-meta-" in html, \
            "card metadata IDs must follow the card-meta-N pattern"


class TestStylesheet:
    """Tests against style.css for theme and contrast requirements."""

    def setup_method(self):
        self.css = _read_path(STATIC_DIR / "style.css")

    def test_theme_toggle_styles_exist(self):
        assert ".theme-toggle" in self.css

    def test_light_theme_exists(self):
        assert '[data-theme="light"]' in self.css

    def test_dark_theme_exists(self):
        assert '[data-theme="dark"]' in self.css

    def test_auto_theme_media_query(self):
        assert "prefers-color-scheme: light" in self.css
        assert ":root:not([data-theme])" in self.css

    def test_amber_badge_variable(self):
        assert "--amber-badge" in self.css
