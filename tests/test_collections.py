"""Tests for named collections support across backends and API."""
from __future__ import annotations

import importlib

import pytest

from alcove.index.embedder import HashEmbedder

_has_zvec = importlib.util.find_spec("zvec") is not None
_skip_zvec = pytest.mark.skipif(not _has_zvec, reason="zvec not available on this platform")


@pytest.fixture()
def embedder():
    return HashEmbedder(dim=32)


# ---------------------------------------------------------------------------
# ChromaBackend collection tests
# ---------------------------------------------------------------------------

class TestChromaCollections:
    def _make_backend(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("CHROMA_COLLECTION", "test_coll")
        from alcove.index.backend import ChromaBackend
        return ChromaBackend(embedder)

    def test_add_default_collection(self, embedder, tmp_path, monkeypatch):
        """Documents without explicit collection get 'default'."""
        backend = self._make_backend(embedder, tmp_path, monkeypatch)
        vecs = embedder.embed(["hello"])
        backend.add(
            ids=["d1"], embeddings=vecs,
            documents=["hello"], metadatas=[{"source": "a.txt"}],
        )
        all_docs = backend._collection.get()
        assert all_docs["metadatas"][0]["collection"] == "default"

    def test_add_explicit_collection(self, embedder, tmp_path, monkeypatch):
        """Documents with explicit collection keep it."""
        backend = self._make_backend(embedder, tmp_path, monkeypatch)
        vecs = embedder.embed(["hello"])
        backend.add(
            ids=["d1"], embeddings=vecs,
            documents=["hello"], metadatas=[{"source": "a.txt", "collection": "poems"}],
        )
        all_docs = backend._collection.get()
        assert all_docs["metadatas"][0]["collection"] == "poems"

    def test_query_with_collection_filter(self, embedder, tmp_path, monkeypatch):
        """Querying with collections= only returns matching docs."""
        backend = self._make_backend(embedder, tmp_path, monkeypatch)
        vecs = embedder.embed(["alpha doc", "beta doc"])
        backend.add(
            ids=["d1", "d2"], embeddings=vecs,
            documents=["alpha doc", "beta doc"],
            metadatas=[
                {"source": "a.txt", "collection": "letters"},
                {"source": "b.txt", "collection": "greek"},
            ],
        )
        q_vec = embedder.embed(["alpha"])[0]
        # Filter to "greek" only
        result = backend.query(q_vec, k=10, collections=["greek"])
        returned_ids = result["ids"][0]
        assert "d2" in returned_ids
        assert "d1" not in returned_ids

    def test_query_without_filter_returns_all(self, embedder, tmp_path, monkeypatch):
        """Querying without collections= returns everything."""
        backend = self._make_backend(embedder, tmp_path, monkeypatch)
        vecs = embedder.embed(["one", "two"])
        backend.add(
            ids=["d1", "d2"], embeddings=vecs,
            documents=["one", "two"],
            metadatas=[
                {"source": "a.txt", "collection": "A"},
                {"source": "b.txt", "collection": "B"},
            ],
        )
        q_vec = embedder.embed(["one"])[0]
        result = backend.query(q_vec, k=10)
        assert len(result["ids"][0]) == 2

    def test_list_collections(self, embedder, tmp_path, monkeypatch):
        """list_collections returns correct names and counts."""
        backend = self._make_backend(embedder, tmp_path, monkeypatch)
        vecs = embedder.embed(["a", "b", "c"])
        backend.add(
            ids=["d1", "d2", "d3"], embeddings=vecs,
            documents=["a", "b", "c"],
            metadatas=[
                {"source": "a.txt", "collection": "X"},
                {"source": "b.txt", "collection": "X"},
                {"source": "c.txt", "collection": "Y"},
            ],
        )
        colls = backend.list_collections()
        by_name = {c["name"]: c["doc_count"] for c in colls}
        assert by_name["X"] == 2
        assert by_name["Y"] == 1

    def test_list_collections_empty(self, embedder, tmp_path, monkeypatch):
        """Empty index returns empty list."""
        backend = self._make_backend(embedder, tmp_path, monkeypatch)
        assert backend.list_collections() == []

    def test_backwards_compat_no_collection_field(self, embedder, tmp_path, monkeypatch):
        """Metadata without collection key defaults to 'default' in listing."""
        backend = self._make_backend(embedder, tmp_path, monkeypatch)
        vecs = embedder.embed(["hello"])
        # add() will set the default
        backend.add(
            ids=["d1"], embeddings=vecs,
            documents=["hello"], metadatas=[{"source": "a.txt"}],
        )
        colls = backend.list_collections()
        assert len(colls) == 1
        assert colls[0]["name"] == "default"
        assert colls[0]["doc_count"] == 1

    def test_query_multiple_collections(self, embedder, tmp_path, monkeypatch):
        """Query filtered to multiple collections returns docs from each."""
        backend = self._make_backend(embedder, tmp_path, monkeypatch)
        vecs = embedder.embed(["a", "b", "c"])
        backend.add(
            ids=["d1", "d2", "d3"], embeddings=vecs,
            documents=["a", "b", "c"],
            metadatas=[
                {"source": "a.txt", "collection": "X"},
                {"source": "b.txt", "collection": "Y"},
                {"source": "c.txt", "collection": "Z"},
            ],
        )
        q_vec = embedder.embed(["a"])[0]
        result = backend.query(q_vec, k=10, collections=["X", "Y"])
        returned_ids = result["ids"][0]
        assert "d1" in returned_ids
        assert "d2" in returned_ids
        assert "d3" not in returned_ids


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestCollectionsAPI:
    def test_collections_endpoint_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.get("/collections")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_collections_endpoint_with_data(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("CHROMA_COLLECTION", "test_api_coll")
        from alcove.index.backend import ChromaBackend
        backend = ChromaBackend(embedder)
        vecs = embedder.embed(["hello", "world"])
        backend.add(
            ids=["d1", "d2"], embeddings=vecs,
            documents=["hello", "world"],
            metadatas=[
                {"source": "a.txt", "collection": "docs"},
                {"source": "b.txt", "collection": "docs"},
            ],
        )
        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.get("/collections")
        assert r.status_code == 200
        data = r.json()
        assert any(c["name"] == "docs" for c in data)

    def test_query_post_with_collections(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.post("/query", json={"query": "test", "k": 1, "collections": ["default"]})
        assert r.status_code == 200

    def test_search_with_collections_param(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.get("/search", params={"q": "test", "collections": "default,other"})
        assert r.status_code == 200

    def test_ingest_with_collection_param(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAW_DIR", str(tmp_path / "raw"))
        monkeypatch.setenv("CHUNKS_FILE", str(tmp_path / "chunks.jsonl"))
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.post(
            "/ingest?collection=my_collection",
            files={"files": ("test.txt", b"some content", "text/plain")},
        )
        assert r.status_code == 200
        data = r.json()
        indexed = [d for d in data if d["status"] == "indexed"]
        if indexed:
            assert indexed[0]["collection"] == "my_collection"
