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
