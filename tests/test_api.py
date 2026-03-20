import os

import pytest
from fastapi.testclient import TestClient

from alcove.query.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_root_returns_html():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Alcove" in r.text
    assert "Lead with the use cases" in r.text
    assert "id=\"workspace\"" in r.text
    assert "alcove seed-demo" in r.text


def test_query_post_returns_json():
    """Query endpoint works even with empty index (returns empty results)."""
    r = client.post("/query", json={"query": "test", "k": 1})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)


def test_ingest_skips_unsupported_format():
    """Unsupported file formats are gracefully skipped (200 with status=skipped), not rejected."""
    r = client.post(
        "/ingest",
        files={"files": ("test.xyz", b"content", "application/octet-stream")},
    )
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["filename"] == "test.xyz"
    assert data[0]["status"] == "skipped"


# ---------------------------------------------------------------------------
# base_url / ALCOVE_ROOT_PATH tests
# ---------------------------------------------------------------------------

class TestRootPathTemplate:
    """Verify ALCOVE_ROOT_PATH injects base_url into rendered HTML."""

    def test_no_root_path_uses_empty_string(self):
        """Without ALCOVE_ROOT_PATH, base_url is '' so CSS href is '/static/style.css'."""
        env_bak = os.environ.pop("ALCOVE_ROOT_PATH", None)
        try:
            r = client.get("/")
            assert r.status_code == 200
            assert 'href="/static/style.css"' in r.text
        finally:
            if env_bak is not None:
                os.environ["ALCOVE_ROOT_PATH"] = env_bak

    def test_root_path_prefixes_static_css(self):
        """With ALCOVE_ROOT_PATH=/demos, CSS href becomes '/demos/static/style.css'."""
        os.environ["ALCOVE_ROOT_PATH"] = "/demos"
        try:
            r = client.get("/")
            assert r.status_code == 200
            assert 'href="/demos/static/style.css"' in r.text
        finally:
            del os.environ["ALCOVE_ROOT_PATH"]

    def test_root_path_prefixes_search_form_action(self):
        """With ALCOVE_ROOT_PATH=/demos, search form action becomes '/demos/search'."""
        os.environ["ALCOVE_ROOT_PATH"] = "/demos"
        try:
            r = client.get("/")
            assert r.status_code == 200
            assert 'action="/demos/search"' in r.text
        finally:
            del os.environ["ALCOVE_ROOT_PATH"]

    def test_root_path_trailing_slash_stripped(self):
        """Trailing slash in ALCOVE_ROOT_PATH is stripped."""
        os.environ["ALCOVE_ROOT_PATH"] = "/demos/"
        try:
            r = client.get("/")
            assert r.status_code == 200
            assert 'href="/demos/static/style.css"' in r.text
            assert 'href="/demos//static/style.css"' not in r.text
        finally:
            del os.environ["ALCOVE_ROOT_PATH"]

    def test_results_back_link_uses_root_path(self):
        """Results page 'Back to search' link respects ALCOVE_ROOT_PATH."""
        os.environ["ALCOVE_ROOT_PATH"] = "/demos"
        try:
            r = client.get("/search?q=test")
            assert r.status_code == 200
            assert 'href="/demos/"' in r.text
        finally:
            del os.environ["ALCOVE_ROOT_PATH"]
