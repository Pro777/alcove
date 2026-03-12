from __future__ import annotations

import importlib

import pytest

from alcove.index.embedder import HashEmbedder

_has_zvec = importlib.util.find_spec("zvec") is not None
_skip_zvec = pytest.mark.skipif(not _has_zvec, reason="zvec not available on this platform")


@pytest.fixture()
def embedder():
    return HashEmbedder(dim=32)


class TestChromaBackend:
    def test_add_and_count(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("CHROMA_COLLECTION", "test_col")
        from alcove.index.backend import ChromaBackend

        backend = ChromaBackend(embedder)
        vecs = embedder.embed(["hello world"])
        backend.add(
            ids=["doc1"],
            embeddings=vecs,
            documents=["hello world"],
            metadatas=[{"source": "test.txt"}],
        )
        assert backend.count() == 1

    def test_query_returns_chromadb_shape(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("CHROMA_COLLECTION", "test_col")
        from alcove.index.backend import ChromaBackend

        backend = ChromaBackend(embedder)
        vecs = embedder.embed(["hello world", "goodbye world"])
        backend.add(
            ids=["d1", "d2"],
            embeddings=vecs,
            documents=["hello world", "goodbye world"],
            metadatas=[{"source": "a.txt"}, {"source": "b.txt"}],
        )
        q_vec = embedder.embed(["hello world"])[0]
        result = backend.query(q_vec, k=2)
        assert "ids" in result
        assert "documents" in result
        assert "distances" in result
        assert len(result["ids"]) == 1  # ChromaDB wraps in outer list
        assert len(result["ids"][0]) == 2

    def test_upsert_overwrites(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("CHROMA_COLLECTION", "test_col")
        from alcove.index.backend import ChromaBackend

        backend = ChromaBackend(embedder)
        vecs = embedder.embed(["version one"])
        backend.add(
            ids=["doc1"],
            embeddings=vecs,
            documents=["version one"],
            metadatas=[{"source": "a.txt"}],
        )
        vecs2 = embedder.embed(["version two"])
        backend.add(
            ids=["doc1"],
            embeddings=vecs2,
            documents=["version two"],
            metadatas=[{"source": "a.txt"}],
        )
        assert backend.count() == 1


@_skip_zvec
class TestZvecBackend:
    def test_add_and_count(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("ZVEC_PATH", str(tmp_path / "zvec"))
        from alcove.index.backend import ZvecBackend

        backend = ZvecBackend(embedder)
        vecs = embedder.embed(["hello world"])
        backend.add(
            ids=["doc1"],
            embeddings=vecs,
            documents=["hello world"],
            metadatas=[{"source": "test.txt"}],
        )
        assert backend.count() == 1

    def test_query_returns_chromadb_shape(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("ZVEC_PATH", str(tmp_path / "zvec"))
        from alcove.index.backend import ZvecBackend

        backend = ZvecBackend(embedder)
        vecs = embedder.embed(["hello world", "goodbye world"])
        backend.add(
            ids=["d1", "d2"],
            embeddings=vecs,
            documents=["hello world", "goodbye world"],
            metadatas=[{"source": "a.txt"}, {"source": "b.txt"}],
        )
        q_vec = embedder.embed(["hello world"])[0]
        result = backend.query(q_vec, k=2)
        assert "ids" in result
        assert "documents" in result
        assert "distances" in result
        assert len(result["ids"]) == 1  # outer list wrapper
        assert len(result["ids"][0]) == 2

    def test_upsert_overwrites(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("ZVEC_PATH", str(tmp_path / "zvec"))
        from alcove.index.backend import ZvecBackend

        backend = ZvecBackend(embedder)
        vecs = embedder.embed(["version one"])
        backend.add(
            ids=["doc1"],
            embeddings=vecs,
            documents=["version one"],
            metadatas=[{"source": "a.txt"}],
        )
        vecs2 = embedder.embed(["version two"])
        backend.add(
            ids=["doc1"],
            embeddings=vecs2,
            documents=["version two"],
            metadatas=[{"source": "a.txt"}],
        )
        assert backend.count() == 1


class TestGetBackend:
    def test_default_is_chromadb(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.delenv("VECTOR_BACKEND", raising=False)
        from alcove.index.backend import ChromaBackend, get_backend

        backend = get_backend(embedder)
        assert isinstance(backend, ChromaBackend)

    def test_chromadb_explicit(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("VECTOR_BACKEND", "chromadb")
        from alcove.index.backend import ChromaBackend, get_backend

        backend = get_backend(embedder)
        assert isinstance(backend, ChromaBackend)

    def test_collection_override_uses_requested_name(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("VECTOR_BACKEND", "chromadb")
        monkeypatch.setenv("CHROMA_COLLECTION", "default_collection")
        from alcove.index.backend import get_backend

        backend = get_backend(embedder, collection_name="regulatory_test_docs")
        backend.add(
            ids=["doc1"],
            embeddings=embedder.embed(["hello world"]),
            documents=["hello world"],
            metadatas=[{"source": "test.txt"}],
        )

        result = backend.query(embedder.embed(["hello world"])[0], k=1)
        assert result["ids"][0] == ["doc1"]

    @_skip_zvec
    def test_zvec_explicit(self, embedder, tmp_path, monkeypatch):
        monkeypatch.setenv("ZVEC_PATH", str(tmp_path / "zvec"))
        monkeypatch.setenv("VECTOR_BACKEND", "zvec")
        from alcove.index.backend import ZvecBackend, get_backend

        backend = get_backend(embedder)
        assert isinstance(backend, ZvecBackend)

    def test_unknown_backend_raises(self, embedder, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "milvus")
        from alcove.index.backend import get_backend

        with pytest.raises(ValueError, match="Unknown.*milvus"):
            get_backend(embedder)
