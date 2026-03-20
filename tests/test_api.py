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


# ---------------------------------------------------------------------------
# Coverage gaps
# ---------------------------------------------------------------------------

def test_demos_index_returns_html():
    """GET /demos renders the demos landing page with content from demos.json."""
    r = client.get("/demos")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # demos.json contains "Congress" — verify the template rendered the catalog
    assert "Congress" in r.text


def test_search_invalid_collection_name_returns_422():
    """GET /search with an invalid collection name (special chars) returns 422."""
    r = client.get("/search", params={"q": "test", "collections": "bad!name"})
    assert r.status_code == 422
    assert "Invalid collection name" in r.json()["detail"]


def test_ingest_disabled_in_demo_mode(monkeypatch):
    """POST /ingest returns 403 when ALCOVE_DEMO_ROOT is set (read-only demo mode)."""
    monkeypatch.setenv("ALCOVE_DEMO_ROOT", "/some/readonly/path")
    r = client.post(
        "/ingest",
        files={"files": ("sample.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 403
    assert "disabled" in r.json()["detail"].lower()


def test_list_collections_backend_exception_returns_empty():
    """GET /collections returns [] gracefully when the backend raises."""
    from unittest.mock import patch
    with patch("alcove.index.backend.get_backend", side_effect=RuntimeError("no db")):
        r = client.get("/collections")
    assert r.status_code == 200
    assert r.json() == []


def test_root_backend_exception_still_renders_html():
    """GET / renders the search page even when the backend raises (doc_count falls back to 0)."""
    from unittest.mock import patch
    with patch("alcove.index.backend.get_backend", side_effect=RuntimeError("no db")):
        r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_demos_index_handles_unreadable_config():
    """GET /demos returns a valid page even when demos.json cannot be read."""
    from pathlib import Path
    from unittest.mock import patch
    original_read = Path.read_text

    def mock_read(self, *args, **kwargs):
        if self.name == "demos.json":
            raise OSError("permission denied")
        return original_read(self, *args, **kwargs)

    with patch.object(Path, "read_text", mock_read):
        r = client.get("/demos")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_demos_index_with_live_collection():
    """GET /demos marks a demo as live when its collection exists in the backend."""
    from unittest.mock import MagicMock, patch
    mock_backend = MagicMock()
    # "congress_summaries" matches the collection in demos.json
    mock_backend.list_collections.return_value = [
        {"name": "congress_summaries", "doc_count": 100}
    ]
    with patch("alcove.index.backend.get_backend", return_value=mock_backend):
        r = client.get("/demos")
    assert r.status_code == 200
    assert "Congress" in r.text


def test_demos_index_backend_exception_still_renders():
    """GET /demos renders even when the backend raises during live-collection resolution."""
    from unittest.mock import patch
    with patch("alcove.index.backend.get_backend", side_effect=RuntimeError("no db")):
        r = client.get("/demos")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
