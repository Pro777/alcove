"""Tests for the ChromaDB collection sync tool (issue #65).

All ChromaDB calls are mocked — no running ChromaDB instance required.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Load module
# ---------------------------------------------------------------------------

_MODULE_PATH = (
    Path(__file__).parent.parent / "tools" / "chroma-sync" / "sync.py"
)


@pytest.fixture(scope="module")
def cs():
    spec = importlib.util.spec_from_file_location("chroma_sync", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["chroma_sync"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helpers for fake ChromaDB objects
# ---------------------------------------------------------------------------

def _make_fake_collection(name: str, records: list[dict], coll_metadata: dict | None = None):
    """Return a mock ChromaDB collection with canned get() output.

    The mock supports paginated access via ``limit`` / ``offset`` kwargs so
    that the paginated export loop terminates correctly.
    """
    ids = [r["id"] for r in records]
    documents = [r.get("document", "") for r in records]
    metadatas = [r.get("metadata", {}) for r in records]
    embeddings = [r.get("embedding", [0.1, 0.2]) for r in records]

    coll = MagicMock()
    coll.name = name
    coll.metadata = coll_metadata or {}
    coll.count.return_value = len(ids)

    def _get(limit=None, offset=0, include=None, **kwargs):
        start = offset or 0
        end = start + limit if limit is not None else len(ids)
        sliced_ids = ids[start:end]
        return {
            "ids": sliced_ids,
            "documents": documents[start:end],
            "metadatas": metadatas[start:end],
            "embeddings": embeddings[start:end],
        }

    coll.get.side_effect = _get
    return coll


def _make_fake_client(collections: dict):
    """Return a mock ChromaDB client that serves the given collections."""
    client = MagicMock()

    def get_collection(name):
        if name not in collections:
            raise Exception(f"Collection {name!r} does not exist")
        return collections[name]

    def get_or_create_collection(name, **kwargs):
        if name not in collections:
            collections[name] = _make_fake_collection(name, [])
        return collections[name]

    client.get_collection.side_effect = get_collection
    client.get_or_create_collection.side_effect = get_or_create_collection
    return client


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_SAMPLE_RECORDS = [
    {"id": "doc:1", "document": "Local RAG systems", "metadata": {"source": "arxiv"}, "embedding": [0.1, 0.2, 0.3]},
    {"id": "doc:2", "document": "Privacy-preserving search", "metadata": {"source": "arxiv"}, "embedding": [0.4, 0.5, 0.6]},
]


# ---------------------------------------------------------------------------
# export_collections
# ---------------------------------------------------------------------------

def test_export_collections_returns_ids(cs):
    coll = _make_fake_collection("arxiv", _SAMPLE_RECORDS)
    client = _make_fake_client({"arxiv": coll})

    result = cs.export_collections(["arxiv"], client_fn=lambda: client)

    assert "arxiv" in result
    assert result["arxiv"]["ids"] == ["doc:1", "doc:2"]


def test_export_collections_preserves_documents(cs):
    coll = _make_fake_collection("arxiv", _SAMPLE_RECORDS)
    client = _make_fake_client({"arxiv": coll})

    result = cs.export_collections(["arxiv"], client_fn=lambda: client)

    assert result["arxiv"]["documents"] == ["Local RAG systems", "Privacy-preserving search"]


def test_export_collections_preserves_embeddings(cs):
    coll = _make_fake_collection("arxiv", _SAMPLE_RECORDS)
    client = _make_fake_client({"arxiv": coll})

    result = cs.export_collections(["arxiv"], client_fn=lambda: client)

    embeddings = result["arxiv"]["embeddings"]
    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2, 0.3]


def test_export_multiple_collections(cs):
    arxiv_coll = _make_fake_collection("arxiv", _SAMPLE_RECORDS)
    psyarxiv_coll = _make_fake_collection("psyarxiv", [
        {"id": "psy:1", "document": "Open science", "metadata": {}, "embedding": [0.7, 0.8]},
    ])
    client = _make_fake_client({"arxiv": arxiv_coll, "psyarxiv": psyarxiv_coll})

    result = cs.export_collections(["arxiv", "psyarxiv"], client_fn=lambda: client)

    assert set(result.keys()) == {"arxiv", "psyarxiv"}
    assert len(result["psyarxiv"]["ids"]) == 1


def test_export_calls_get_with_embeddings(cs):
    coll = _make_fake_collection("arxiv", _SAMPLE_RECORDS)
    client = _make_fake_client({"arxiv": coll})

    cs.export_collections(["arxiv"], client_fn=lambda: client)

    call_args = coll.get.call_args
    assert "embeddings" in call_args.kwargs.get("include", [])


def test_export_includes_collection_metadata(cs):
    coll = _make_fake_collection("arxiv", _SAMPLE_RECORDS, coll_metadata={"hnsw:space": "cosine"})
    client = _make_fake_client({"arxiv": coll})

    result = cs.export_collections(["arxiv"], client_fn=lambda: client)

    assert result["arxiv"]["metadata"] == {"hnsw:space": "cosine"}


def test_export_paginates_large_collection(cs):
    """Export fetches records in pages, not all at once."""
    n = cs.EXPORT_BATCH_SIZE + 5
    records = [{"id": f"id:{i}", "document": f"doc {i}", "embedding": [float(i)]} for i in range(n)]
    coll = _make_fake_collection("big", records)
    client = _make_fake_client({"big": coll})

    result = cs.export_collections(["big"], client_fn=lambda: client)

    assert len(result["big"]["ids"]) == n
    # count() called once; get() called twice (two pages)
    coll.count.assert_called_once()
    assert coll.get.call_count == 2


# ---------------------------------------------------------------------------
# write_dump / read_dump
# ---------------------------------------------------------------------------

def test_write_dump_creates_file(cs, tmp_path):
    data = {"arxiv": {"ids": ["a"], "documents": ["d"], "metadatas": [{}], "embeddings": [[0.1]]}}
    out = tmp_path / "dump.json"
    cs.write_dump(data, out)
    assert out.exists()


def test_write_dump_valid_json(cs, tmp_path):
    data = {"arxiv": {"ids": ["a"], "documents": ["d"], "metadatas": [{}], "embeddings": [[0.1]]}}
    out = tmp_path / "dump.json"
    cs.write_dump(data, out)
    loaded = json.loads(out.read_text())
    assert loaded["alcove_sync_version"] == 1
    assert "exported_at" in loaded
    assert "collections" in loaded


def test_read_dump_roundtrip(cs, tmp_path):
    data = {"arxiv": {"ids": ["x"], "documents": ["doc"], "metadatas": [{"k": "v"}], "embeddings": [[1.0]]}}
    out = tmp_path / "dump.json"
    cs.write_dump(data, out)
    loaded = cs.read_dump(out)
    assert loaded["collections"]["arxiv"]["ids"] == ["x"]


def test_read_dump_raises_on_wrong_version(cs, tmp_path):
    dump_path = tmp_path / "bad.json"
    dump_path.write_text(json.dumps({"alcove_sync_version": 99, "collections": {}}))
    with pytest.raises(ValueError, match="Unsupported dump version"):
        cs.read_dump(dump_path)


# ---------------------------------------------------------------------------
# import_collections
# ---------------------------------------------------------------------------

def test_import_creates_collections(cs, tmp_path):
    dump = {
        "alcove_sync_version": 1,
        "exported_at": "2026-03-19T10:00:00Z",
        "collections": {
            "arxiv": {
                "ids": ["doc:1", "doc:2"],
                "documents": ["Local RAG", "Privacy search"],
                "metadatas": [{"source": "arxiv"}, {"source": "arxiv"}],
                "embeddings": [[0.1, 0.2], [0.3, 0.4]],
            }
        },
    }
    target_coll = MagicMock()
    target_client = MagicMock()
    target_client.get_or_create_collection.return_value = target_coll

    counts = cs.import_collections(dump, client_fn=lambda: target_client)

    assert counts["arxiv"] == 2
    target_coll.upsert.assert_called_once()


def test_import_upserts_with_embeddings(cs):
    dump = {
        "alcove_sync_version": 1,
        "exported_at": "2026-03-19T10:00:00Z",
        "collections": {
            "arxiv": {
                "ids": ["a"],
                "documents": ["hello"],
                "metadatas": [{}],
                "embeddings": [[0.5, 0.6]],
            }
        },
    }
    target_coll = MagicMock()
    target_client = MagicMock()
    target_client.get_or_create_collection.return_value = target_coll

    cs.import_collections(dump, client_fn=lambda: target_client)

    call_kwargs = target_coll.upsert.call_args.kwargs
    assert "embeddings" in call_kwargs
    assert call_kwargs["embeddings"] == [[0.5, 0.6]]


def test_import_skips_empty_collection(cs):
    dump = {
        "alcove_sync_version": 1,
        "exported_at": "2026-03-19T10:00:00Z",
        "collections": {
            "empty": {"ids": [], "documents": [], "metadatas": [], "embeddings": []},
        },
    }
    target_coll = MagicMock()
    target_client = MagicMock()
    target_client.get_or_create_collection.return_value = target_coll

    counts = cs.import_collections(dump, client_fn=lambda: target_client)

    assert counts["empty"] == 0
    target_coll.upsert.assert_not_called()


def test_import_passes_collection_metadata(cs):
    """get_or_create_collection is called with the collection metadata from the dump."""
    dump = {
        "alcove_sync_version": 1,
        "exported_at": "2026-03-19T10:00:00Z",
        "collections": {
            "arxiv": {
                "metadata": {"hnsw:space": "cosine"},
                "ids": ["a"],
                "documents": ["hello"],
                "metadatas": [{}],
                "embeddings": [[0.5, 0.6]],
            }
        },
    }
    target_coll = MagicMock()
    target_client = MagicMock()
    target_client.get_or_create_collection.return_value = target_coll

    cs.import_collections(dump, client_fn=lambda: target_client)

    target_client.get_or_create_collection.assert_called_once_with(
        "arxiv", metadata={"hnsw:space": "cosine"}
    )


def test_import_batches_large_collections(cs):
    """Upsert is called multiple times when record count exceeds IMPORT_BATCH_SIZE."""
    n = cs.IMPORT_BATCH_SIZE + 10
    dump = {
        "alcove_sync_version": 1,
        "exported_at": "2026-03-19T10:00:00Z",
        "collections": {
            "big": {
                "ids": [f"id:{i}" for i in range(n)],
                "documents": [f"doc {i}" for i in range(n)],
                "metadatas": [{} for _ in range(n)],
                "embeddings": [[float(i)] for i in range(n)],
            }
        },
    }
    target_coll = MagicMock()
    target_client = MagicMock()
    target_client.get_or_create_collection.return_value = target_coll

    counts = cs.import_collections(dump, client_fn=lambda: target_client)

    assert counts["big"] == n
    assert target_coll.upsert.call_count == 2  # batch 1 + batch 2


# ---------------------------------------------------------------------------
# Roundtrip: export → dump → import
# ---------------------------------------------------------------------------

def test_export_import_roundtrip(cs, tmp_path):
    """Full roundtrip: exported records appear in target collection."""
    src_coll = _make_fake_collection("arxiv", _SAMPLE_RECORDS)
    src_client = _make_fake_client({"arxiv": src_coll})

    # Export
    exported = cs.export_collections(["arxiv"], client_fn=lambda: src_client)
    dump_path = tmp_path / "sync.json"
    cs.write_dump(exported, dump_path)

    # Import
    dump = cs.read_dump(dump_path)
    dst_coll = MagicMock()
    dst_client = MagicMock()
    dst_client.get_or_create_collection.return_value = dst_coll

    counts = cs.import_collections(dump, client_fn=lambda: dst_client)

    assert counts["arxiv"] == 2
    upsert_ids = dst_coll.upsert.call_args.kwargs["ids"]
    assert "doc:1" in upsert_ids and "doc:2" in upsert_ids
