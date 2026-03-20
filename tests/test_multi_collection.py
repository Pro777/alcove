"""Tests for MultiChromaBackend — multi-collection fan-out support."""
from __future__ import annotations

import pytest

from alcove.index.embedder import HashEmbedder


@pytest.fixture()
def embedder():
    return HashEmbedder(dim=32)


def _make_multi_backend(embedder, tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
    from alcove.index.backend import MultiChromaBackend
    return MultiChromaBackend(embedder)


def _seed_collection(client, col_name, embedder, docs):
    """Helper: create a ChromaDB collection and add docs."""
    import chromadb
    col = client.get_or_create_collection(name=col_name)
    ids = [f"{col_name}-{i}" for i in range(len(docs))]
    vecs = embedder.embed(docs)
    metas = [{"source": f"{col_name}-doc-{i}.txt", "collection": col_name} for i in range(len(docs))]
    col.upsert(ids=ids, embeddings=vecs, documents=docs, metadatas=metas)
    return col


class TestMultiChromaBackend:
    def test_list_collections_empty(self, embedder, tmp_path, monkeypatch):
        """Empty chroma path returns empty list."""
        backend = _make_multi_backend(embedder, tmp_path, monkeypatch)
        assert backend.list_collections() == []

    def test_list_collections_multiple(self, embedder, tmp_path, monkeypatch):
        """list_collections returns one entry per ChromaDB collection."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "alpha", embedder, ["doc one", "doc two"])
        _seed_collection(client, "beta", embedder, ["doc three"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
        from alcove.index.backend import MultiChromaBackend
        backend = MultiChromaBackend(embedder)

        colls = backend.list_collections()
        by_name = {c["name"]: c["doc_count"] for c in colls}
        assert "alpha" in by_name
        assert "beta" in by_name
        assert by_name["alpha"] == 2
        assert by_name["beta"] == 1

    def test_count_sums_all_collections(self, embedder, tmp_path, monkeypatch):
        """count() returns total across all ChromaDB collections."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "col1", embedder, ["a", "b", "c"])
        _seed_collection(client, "col2", embedder, ["d", "e"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
        from alcove.index.backend import MultiChromaBackend
        backend = MultiChromaBackend(embedder)

        assert backend.count() == 5

    def test_query_fans_out_to_all_collections(self, embedder, tmp_path, monkeypatch):
        """query() with no filter returns results from all collections."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "mnhs", embedder, ["minnesota history document"])
        _seed_collection(client, "cyan", embedder, ["guild of archivists lore"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
        from alcove.index.backend import MultiChromaBackend
        backend = MultiChromaBackend(embedder)

        q_vec = embedder.embed(["history"])[0]
        result = backend.query(q_vec, k=5)
        assert "ids" in result
        assert "documents" in result
        assert "distances" in result
        assert "metadatas" in result
        all_ids = result["ids"][0]
        # Should get at least one result from each collection
        mnhs_ids = [i for i in all_ids if i.startswith("mnhs")]
        cyan_ids = [i for i in all_ids if i.startswith("cyan")]
        assert len(mnhs_ids) >= 1
        assert len(cyan_ids) >= 1

    def test_query_filtered_to_single_collection(self, embedder, tmp_path, monkeypatch):
        """query() with collections= only returns from matching ChromaDB collections."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "mnhs", embedder, ["minnesota history"])
        _seed_collection(client, "cyan", embedder, ["guild of archivists"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
        from alcove.index.backend import MultiChromaBackend
        backend = MultiChromaBackend(embedder)

        q_vec = embedder.embed(["history"])[0]
        result = backend.query(q_vec, k=5, collections=["mnhs"])
        all_ids = result["ids"][0]
        cyan_ids = [i for i in all_ids if i.startswith("cyan")]
        assert len(cyan_ids) == 0
        mnhs_ids = [i for i in all_ids if i.startswith("mnhs")]
        assert len(mnhs_ids) >= 1

    def test_query_returns_chromadb_shape(self, embedder, tmp_path, monkeypatch):
        """query() output has the standard ChromaDB shape (outer list wrapper)."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "testcol", embedder, ["hello world"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
        from alcove.index.backend import MultiChromaBackend
        backend = MultiChromaBackend(embedder)

        q_vec = embedder.embed(["hello"])[0]
        result = backend.query(q_vec, k=3)
        assert isinstance(result["ids"], list)
        assert isinstance(result["ids"][0], list)
        assert isinstance(result["documents"], list)
        assert isinstance(result["documents"][0], list)
        assert isinstance(result["distances"], list)
        assert isinstance(result["distances"][0], list)

    def test_query_empty_backend_returns_empty(self, embedder, tmp_path, monkeypatch):
        """query() on empty backend returns empty result sets."""
        backend = _make_multi_backend(embedder, tmp_path, monkeypatch)
        q_vec = embedder.embed(["anything"])[0]
        result = backend.query(q_vec, k=5)
        assert result["ids"] == [[]]
        assert result["documents"] == [[]]
        assert result["distances"] == [[]]

    def test_query_respects_k_limit(self, embedder, tmp_path, monkeypatch):
        """query() returns at most k results total."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "colA", embedder, ["doc a1", "doc a2", "doc a3"])
        _seed_collection(client, "colB", embedder, ["doc b1", "doc b2", "doc b3"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
        from alcove.index.backend import MultiChromaBackend
        backend = MultiChromaBackend(embedder)

        q_vec = embedder.embed(["doc"])[0]
        result = backend.query(q_vec, k=3)
        assert len(result["ids"][0]) <= 3

    def test_metadatas_include_collection_name(self, embedder, tmp_path, monkeypatch):
        """Results from MultiChromaBackend include collection name in metadata."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "mydata", embedder, ["sample document"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
        from alcove.index.backend import MultiChromaBackend
        backend = MultiChromaBackend(embedder)

        q_vec = embedder.embed(["sample"])[0]
        result = backend.query(q_vec, k=5)
        metas = result["metadatas"][0]
        assert len(metas) >= 1
        for meta in metas:
            assert "collection" in meta


class TestMultiRootBackend:
    """Tests for MultiRootBackend — one ChromaDB dir per subdirectory."""

    def _seed_root(self, root, embedder, collections: dict):
        """Create subdirs with chroma/ contents.
        collections = {name: [doc, doc, ...]}
        """
        import chromadb
        from chromadb.config import Settings
        for name, docs in collections.items():
            chroma_dir = root / name / "chroma"
            chroma_dir.mkdir(parents=True)
            client = chromadb.PersistentClient(path=str(chroma_dir), settings=Settings(anonymized_telemetry=False))
            col = client.get_or_create_collection(name=name)
            ids = [f"{name}-{i}" for i in range(len(docs))]
            vecs = embedder.embed(docs)
            metas = [{"source": f"{name}-{i}.txt", "collection": name} for i in range(len(docs))]
            col.upsert(ids=ids, embeddings=vecs, documents=docs, metadatas=metas)

    def test_list_collections_from_subdirs(self, embedder, tmp_path, monkeypatch):
        """list_collections returns one entry per subdirectory with chroma/."""
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {
            "mnhs": ["history doc 1", "history doc 2"],
            "cyan": ["lore doc 1"],
        })
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))
        from alcove.index.backend import MultiRootBackend
        backend = MultiRootBackend(embedder)
        colls = backend.list_collections()
        by_name = {c["name"]: c["doc_count"] for c in colls}
        assert "mnhs" in by_name
        assert "cyan" in by_name
        assert by_name["mnhs"] == 2
        assert by_name["cyan"] == 1

    def test_count_sums_subdirs(self, embedder, tmp_path, monkeypatch):
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {
            "colA": ["a", "b"],
            "colB": ["c", "d", "e"],
        })
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))
        from alcove.index.backend import MultiRootBackend
        backend = MultiRootBackend(embedder)
        assert backend.count() == 5

    def test_query_fans_out_to_all_subdirs(self, embedder, tmp_path, monkeypatch):
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {
            "mnhs": ["minnesota history"],
            "cyan": ["guild of archivists"],
        })
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))
        from alcove.index.backend import MultiRootBackend
        backend = MultiRootBackend(embedder)

        q_vec = embedder.embed(["history"])[0]
        result = backend.query(q_vec, k=5)
        all_ids = result["ids"][0]
        mnhs_ids = [i for i in all_ids if i.startswith("mnhs")]
        cyan_ids = [i for i in all_ids if i.startswith("cyan")]
        assert len(mnhs_ids) >= 1
        assert len(cyan_ids) >= 1

    def test_query_filtered_by_collection(self, embedder, tmp_path, monkeypatch):
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {
            "mnhs": ["minnesota history"],
            "cyan": ["guild lore"],
        })
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))
        from alcove.index.backend import MultiRootBackend
        backend = MultiRootBackend(embedder)

        q_vec = embedder.embed(["history"])[0]
        result = backend.query(q_vec, k=5, collections=["mnhs"])
        all_ids = result["ids"][0]
        cyan_ids = [i for i in all_ids if i.startswith("cyan")]
        assert len(cyan_ids) == 0

    def test_empty_subdir_skipped(self, embedder, tmp_path, monkeypatch):
        """Subdirs without chroma/ are skipped gracefully."""
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {"mnhs": ["doc"]})
        (root / "not-a-collection").mkdir()  # no chroma/ inside
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))
        from alcove.index.backend import MultiRootBackend
        backend = MultiRootBackend(embedder)
        colls = backend.list_collections()
        names = {c["name"] for c in colls}
        assert "not-a-collection" not in names
        assert "mnhs" in names

    def test_query_returns_chromadb_shape(self, embedder, tmp_path, monkeypatch):
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {"testcol": ["hello world"]})
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))
        from alcove.index.backend import MultiRootBackend
        backend = MultiRootBackend(embedder)

        q_vec = embedder.embed(["hello"])[0]
        result = backend.query(q_vec, k=3)
        assert isinstance(result["ids"], list)
        assert isinstance(result["ids"][0], list)
        assert isinstance(result["metadatas"][0], list)

    def test_metadatas_include_collection_name(self, embedder, tmp_path, monkeypatch):
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {"mydata": ["sample"]})
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))
        from alcove.index.backend import MultiRootBackend
        backend = MultiRootBackend(embedder)

        q_vec = embedder.embed(["sample"])[0]
        result = backend.query(q_vec, k=5)
        for meta in result["metadatas"][0]:
            assert "collection" in meta


class TestGetBackendMultiCollectionActivation:
    def test_multi_collection_env_activates_multi_backend(self, embedder, tmp_path, monkeypatch):
        """ALCOVE_MULTI_COLLECTION=1 returns MultiChromaBackend."""
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")
        monkeypatch.delenv("VECTOR_BACKEND", raising=False)
        from alcove.index.backend import MultiChromaBackend, get_backend
        backend = get_backend(embedder)
        assert isinstance(backend, MultiChromaBackend)

    def test_star_collection_activates_multi_backend(self, embedder, tmp_path, monkeypatch):
        """CHROMA_COLLECTION=* returns MultiChromaBackend."""
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("CHROMA_COLLECTION", "*")
        monkeypatch.delenv("ALCOVE_MULTI_COLLECTION", raising=False)
        monkeypatch.delenv("VECTOR_BACKEND", raising=False)
        from alcove.index.backend import MultiChromaBackend, get_backend
        backend = get_backend(embedder)
        assert isinstance(backend, MultiChromaBackend)

    def test_normal_env_returns_single_chromabackend(self, embedder, tmp_path, monkeypatch):
        """Without multi-collection flags, get_backend returns ChromaBackend."""
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.delenv("ALCOVE_MULTI_COLLECTION", raising=False)
        monkeypatch.delenv("CHROMA_COLLECTION", raising=False)
        monkeypatch.delenv("VECTOR_BACKEND", raising=False)
        from alcove.index.backend import ChromaBackend, get_backend
        backend = get_backend(embedder)
        assert isinstance(backend, ChromaBackend)

    def test_multi_collection_false_values_dont_activate(self, embedder, tmp_path, monkeypatch):
        """ALCOVE_MULTI_COLLECTION=0 does not activate multi backend."""
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "0")
        monkeypatch.delenv("VECTOR_BACKEND", raising=False)
        from alcove.index.backend import ChromaBackend, get_backend
        backend = get_backend(embedder)
        assert isinstance(backend, ChromaBackend)

    def test_demo_root_activates_multi_root_backend(self, embedder, tmp_path, monkeypatch):
        """ALCOVE_DEMO_ROOT set returns MultiRootBackend."""
        root = tmp_path / "collections"
        root.mkdir()
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))
        monkeypatch.delenv("VECTOR_BACKEND", raising=False)
        from alcove.index.backend import MultiRootBackend, get_backend
        backend = get_backend(embedder)
        assert isinstance(backend, MultiRootBackend)


class TestMultiCollectionAPI:
    def test_collections_endpoint_returns_chroma_collections(self, embedder, tmp_path, monkeypatch):
        """With multi-collection mode, /collections returns ChromaDB collection names."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "mnhs", embedder, ["doc one", "doc two"])
        _seed_collection(client, "cyan", embedder, ["doc three"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client_api = TestClient(app)
        r = client_api.get("/collections")
        assert r.status_code == 200
        data = r.json()
        names = {c["name"] for c in data}
        assert "mnhs" in names
        assert "cyan" in names

    def test_search_with_collection_filter_multi_mode(self, embedder, tmp_path, monkeypatch):
        """GET /search?collections=mnhs works in multi-collection mode."""
        import chromadb
        from chromadb.config import Settings
        chroma_path = str(tmp_path / "chroma")
        client = chromadb.PersistentClient(path=chroma_path, settings=Settings(anonymized_telemetry=False))
        _seed_collection(client, "mnhs", embedder, ["history document"])

        monkeypatch.setenv("CHROMA_PATH", chroma_path)
        monkeypatch.setenv("ALCOVE_MULTI_COLLECTION", "1")

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client_api = TestClient(app)
        r = client_api.get("/search", params={"q": "history", "collections": "mnhs"})
        assert r.status_code == 200


class TestMultiRootAPI:
    def _seed_root(self, root, embedder, collections: dict):
        import chromadb
        from chromadb.config import Settings
        for name, docs in collections.items():
            chroma_dir = root / name / "chroma"
            chroma_dir.mkdir(parents=True)
            client = chromadb.PersistentClient(path=str(chroma_dir), settings=Settings(anonymized_telemetry=False))
            col = client.get_or_create_collection(name=name)
            ids = [f"{name}-{i}" for i in range(len(docs))]
            vecs = embedder.embed(docs)
            metas = [{"source": f"{name}-{i}.txt", "collection": name} for i in range(len(docs))]
            col.upsert(ids=ids, embeddings=vecs, documents=docs, metadatas=metas)

    def test_collections_endpoint_returns_subdir_names(self, embedder, tmp_path, monkeypatch):
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {
            "mnhs": ["history doc"],
            "cyan": ["lore doc"],
        })
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client_api = TestClient(app)
        r = client_api.get("/collections")
        assert r.status_code == 200
        data = r.json()
        names = {c["name"] for c in data}
        assert "mnhs" in names
        assert "cyan" in names

    def test_search_endpoint_works_with_demo_root(self, embedder, tmp_path, monkeypatch):
        root = tmp_path / "collections"
        self._seed_root(root, embedder, {"mnhs": ["history document"]})
        monkeypatch.setenv("ALCOVE_DEMO_ROOT", str(root))

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client_api = TestClient(app)
        r = client_api.get("/search", params={"q": "history", "collections": "mnhs"})
        assert r.status_code == 200
