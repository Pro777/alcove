import json

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


def test_search_results_render_clickable_document_links(monkeypatch):
    def fake_query_text(query, k):
        assert query == "Beta note"
        assert k == 5
        return {
            "documents": [["Beta note appears in this document alongside other context that should be excerpted."]],
            "metadatas": [[{"source": "data/raw/Beta Notes.txt"}]],
            "distances": [[0.12]],
        }

    monkeypatch.setattr("alcove.query.api.query_text", fake_query_text)

    r = client.get("/search", params={"q": "Beta note"})

    assert r.status_code == 200
    assert 'href="/document?source=data%2Fraw%2FBeta%20Notes.txt"' in r.text
    assert 'target="_blank"' in r.text
    assert "<mark>Beta</mark>" in r.text
    assert "<mark>note</mark>" in r.text or "<mark>Notes</mark>" in r.text
    assert "Open document" in r.text


def test_document_route_serves_indexed_source(monkeypatch, tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("hello from alcove", encoding="utf-8")
    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        json.dumps({"source": str(source), "chunk": "hello", "id": "notes:0"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CHUNKS_FILE", str(chunks_file))

    r = client.get("/document", params={"source": str(source)})

    assert r.status_code == 200
    assert r.content == b"hello from alcove"


def test_document_route_rejects_unindexed_source(monkeypatch, tmp_path):
    source = tmp_path / "private.txt"
    source.write_text("not indexed", encoding="utf-8")
    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text(
        json.dumps({"source": str(tmp_path / "other.txt"), "chunk": "other", "id": "other:0"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CHUNKS_FILE", str(chunks_file))

    r = client.get("/document", params={"source": str(source)})

    assert r.status_code == 404
