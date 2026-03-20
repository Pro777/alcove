from __future__ import annotations

import os
from typing import Dict, List, Optional

import chromadb
from chromadb.config import Settings

from .embedder import get_collection_name


class MultiChromaBackend:
    """Vector backend that fans out across ALL ChromaDB collections in CHROMA_PATH.

    Activated when CHROMA_COLLECTION=* or ALCOVE_MULTI_COLLECTION=1.
    Each named ChromaDB collection is treated as a top-level collection visible
    in the UI picker. Queries are fanned out and results merged by distance.
    """

    def __init__(self, embedder):
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        self._chroma_path = os.getenv("CHROMA_PATH", "./data/chroma")
        self._embedder = embedder
        self._client = chromadb.PersistentClient(
            path=self._chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )

    def _list_collection_names(self) -> List[str]:
        """Return all ChromaDB collection names (compatible with v0.5 and v0.6+)."""
        raw = self._client.list_collections()
        # ChromaDB v0.6+: returns list of strings
        # ChromaDB v0.5: returns list of Collection objects
        if raw and not isinstance(raw[0], str):
            return [c.name for c in raw]
        return list(raw)

    def _get_all_collections(self):
        """Return all ChromaDB collection objects."""
        names = self._list_collection_names()
        cols = []
        for name in names:
            try:
                cols.append(self._client.get_collection(name=name))
            except Exception:
                continue
        return cols

    def _get_filtered_collections(self, names: Optional[List[str]] = None):
        """Return collection objects, optionally filtered by name list."""
        all_names = self._list_collection_names()
        if names:
            name_set = set(names)
            all_names = [n for n in all_names if n in name_set]
        cols = []
        for name in all_names:
            try:
                cols.append(self._client.get_collection(name=name))
            except Exception:
                continue
        return cols

    def add(self, ids, embeddings, documents, metadatas):
        """Add documents, routing each item to its logical collection from metadata."""
        default_logical = os.getenv("CHROMA_COLLECTION", "alcove_docs")
        # Group by logical collection name from per-item metadata
        groups: dict = {}
        for i, meta in enumerate(metadatas):
            logical = meta.get("collection") or default_logical
            if logical not in groups:
                groups[logical] = {"ids": [], "embeddings": [], "documents": [], "metadatas": []}
            meta.setdefault("collection", logical)
            groups[logical]["ids"].append(ids[i])
            groups[logical]["embeddings"].append(embeddings[i])
            groups[logical]["documents"].append(documents[i])
            groups[logical]["metadatas"].append(meta)
        for logical, group in groups.items():
            physical = get_collection_name(logical)
            col = self._client.get_or_create_collection(name=physical)
            col.upsert(
                ids=group["ids"],
                documents=group["documents"],
                metadatas=group["metadatas"],
                embeddings=group["embeddings"],
            )

    def query(self, embedding, k=3, collections: Optional[List[str]] = None):
        """Fan out query to all (or filtered) collections and merge by distance."""
        target_cols = self._get_filtered_collections(collections)
        if not target_cols:
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}

        merged_ids: List[str] = []
        merged_docs: List[str] = []
        merged_dists: List[float] = []
        merged_metas: List[dict] = []

        for col in target_cols:
            try:
                col_count = col.count()
                if col_count == 0:
                    continue
                n = min(k, col_count)
                result = col.query(
                    query_embeddings=[embedding],
                    n_results=n,
                    include=["documents", "distances", "metadatas"],
                )
                ids = result.get("ids", [[]])[0]
                docs = result.get("documents", [[]])[0]
                dists = result.get("distances", [[]])[0]
                metas = result.get("metadatas", [[]])[0]
                for i, (doc_id, doc, dist) in enumerate(zip(ids, docs, dists)):
                    meta = metas[i] if i < len(metas) else {}
                    if isinstance(meta, dict):
                        meta = dict(meta)
                    else:
                        meta = {}
                    meta.setdefault("collection", col.name)
                    merged_ids.append(doc_id)
                    merged_docs.append(doc)
                    merged_dists.append(dist)
                    merged_metas.append(meta)
            except Exception:
                continue

        # Sort by distance ascending (lower = better match in ChromaDB)
        combined = sorted(
            zip(merged_ids, merged_docs, merged_dists, merged_metas),
            key=lambda x: x[2],
        )[:k]

        if not combined:
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}

        out_ids, out_docs, out_dists, out_metas = zip(*combined)
        return {
            "ids": [list(out_ids)],
            "documents": [list(out_docs)],
            "distances": [list(out_dists)],
            "metadatas": [list(out_metas)],
        }

    def count(self) -> int:
        """Return total document count across all collections."""
        return sum(c.count() for c in self._get_all_collections())

    def list_collections(self) -> List[Dict[str, object]]:
        """Return one entry per ChromaDB collection with its document count."""
        cols = self._get_all_collections()
        result = []
        for col in sorted(cols, key=lambda c: c.name):
            result.append({"name": col.name, "doc_count": col.count()})
        return result


class MultiRootBackend:
    """Vector backend that fans out across multiple ChromaDB directories.

    Activated when ALCOVE_DEMO_ROOT is set to a directory whose subdirectories
    each contain a ``chroma/`` folder.  Each subdirectory becomes a named
    collection in the UI.  Queries are fanned out to all (or filtered)
    subdirectory clients and results merged by distance.
    """

    def __init__(self, embedder):
        import pathlib
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        self._embedder = embedder
        root = pathlib.Path(os.environ["ALCOVE_DEMO_ROOT"]).expanduser()
        # Build ordered list of (collection_name, chromadb_client, chroma_collection)
        self._cols: List[tuple] = []
        for subdir in sorted(root.iterdir()):
            chroma_dir = subdir / "chroma"
            if not subdir.is_dir() or not chroma_dir.is_dir():
                continue
            try:
                client = chromadb.PersistentClient(
                    path=str(chroma_dir),
                    settings=Settings(anonymized_telemetry=False),
                )
                raw_cols = client.list_collections()
                if not raw_cols:
                    continue
                # ChromaDB v0.6+: list_collections returns strings; v0.5: objects
                if raw_cols and not isinstance(raw_cols[0], str):
                    col_names = [c.name for c in raw_cols]
                else:
                    col_names = list(raw_cols)
                # Map logical subdir name to physical collection name via embedder prefix
                name = subdir.name
                physical_name = get_collection_name(name)
                if physical_name in col_names:
                    target_name = physical_name
                elif name in col_names:
                    target_name = name
                else:
                    continue
                matched = client.get_collection(name=target_name)
                self._cols.append((name, client, matched))
            except Exception:
                continue

    def add(self, ids, embeddings, documents, metadatas):  # pragma: no cover
        raise NotImplementedError("MultiRootBackend is read-only; ingest each collection separately.")

    def query(self, embedding, k=3, collections: Optional[List[str]] = None):
        """Fan out query across all (or filtered) roots and merge by distance."""
        targets = self._cols
        if collections:
            name_set = set(collections)
            targets = [(n, cl, col) for n, cl, col in self._cols if n in name_set]

        merged_ids: List[str] = []
        merged_docs: List[str] = []
        merged_dists: List[float] = []
        merged_metas: List[dict] = []

        for coll_name, _client, col in targets:
            try:
                col_count = col.count()
                if col_count == 0:
                    continue
                n = min(k, col_count)
                result = col.query(
                    query_embeddings=[embedding],
                    n_results=n,
                    include=["documents", "distances", "metadatas"],
                )
                ids = result.get("ids", [[]])[0]
                docs = result.get("documents", [[]])[0]
                dists = result.get("distances", [[]])[0]
                metas = result.get("metadatas", [[]])[0]
                for i, (doc_id, doc, dist) in enumerate(zip(ids, docs, dists)):
                    meta = dict(metas[i]) if i < len(metas) and isinstance(metas[i], dict) else {}
                    meta.setdefault("collection", coll_name)
                    merged_ids.append(doc_id)
                    merged_docs.append(doc)
                    merged_dists.append(dist)
                    merged_metas.append(meta)
            except Exception:
                continue

        combined = sorted(
            zip(merged_ids, merged_docs, merged_dists, merged_metas),
            key=lambda x: x[2],
        )[:k]

        if not combined:
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}

        out_ids, out_docs, out_dists, out_metas = zip(*combined)
        return {
            "ids": [list(out_ids)],
            "documents": [list(out_docs)],
            "distances": [list(out_dists)],
            "metadatas": [list(out_metas)],
        }

    def count(self) -> int:
        return sum(col.count() for _, _, col in self._cols)

    def list_collections(self) -> List[Dict[str, object]]:
        return [{"name": name, "doc_count": col.count()} for name, _, col in self._cols]


class ChromaBackend:
    """Vector backend backed by local ChromaDB."""

    def __init__(self, embedder):
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
        chroma_path = os.getenv("CHROMA_PATH", "./data/chroma")
        collection_name = get_collection_name(os.getenv("CHROMA_COLLECTION", "alcove_docs"))
        client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = client.get_or_create_collection(name=collection_name)

    def add(self, ids, embeddings, documents, metadatas):
        # Ensure every metadata dict has a "collection" key.
        for meta in metadatas:
            meta.setdefault("collection", "default")
        self._collection.upsert(
            ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings,
        )

    def query(self, embedding, k=3, collections: Optional[List[str]] = None):
        kwargs: dict = {"query_embeddings": [embedding], "n_results": k}
        if collections:
            kwargs["where"] = {"collection": {"$in": collections}}
        return self._collection.query(**kwargs)

    def count(self):
        return self._collection.count()

    def list_collections(self) -> List[Dict[str, object]]:
        """Return distinct collection names with document counts."""
        all_docs = self._collection.get(include=["metadatas"])
        counts: Dict[str, int] = {}
        for meta in (all_docs.get("metadatas") or []):
            name = (meta or {}).get("collection", "default")
            counts[name] = counts.get(name, 0) + 1
        return [{"name": n, "doc_count": c} for n, c in sorted(counts.items())]


class ZvecBackend:
    """Vector backend backed by local zvec."""

    def __init__(self, embedder):
        import zvec as _zvec
        self._zvec = _zvec

        zvec_path = os.getenv("ZVEC_PATH", "./data/zvec")
        collection_name = get_collection_name(os.getenv("CHROMA_COLLECTION", "alcove_docs"))
        self._path = os.path.join(zvec_path, collection_name)
        self._dim = embedder.dim

        try:
            self._collection = _zvec.open(
                path=self._path, option=_zvec.CollectionOption(),
            )
        except Exception:
            schema = _zvec.CollectionSchema(
                name=collection_name,
                fields=[
                    _zvec.FieldSchema("document", _zvec.DataType.STRING),
                    _zvec.FieldSchema("source", _zvec.DataType.STRING),
                    _zvec.FieldSchema("collection", _zvec.DataType.STRING),
                ],
                vectors=_zvec.VectorSchema(
                    "embedding", _zvec.DataType.VECTOR_FP32, dimension=self._dim,
                ),
            )
            self._collection = _zvec.create_and_open(
                path=self._path, schema=schema, option=_zvec.CollectionOption(),
            )

    def add(self, ids, embeddings, documents, metadatas):
        _zvec = self._zvec
        docs = []
        for i, id_ in enumerate(ids):
            coll = metadatas[i].get("collection", "default")
            docs.append(
                _zvec.Doc(
                    id=id_,
                    vectors={"embedding": embeddings[i]},
                    fields={
                        "document": documents[i],
                        "source": metadatas[i].get("source", ""),
                        "collection": coll,
                    },
                )
            )
        self._collection.upsert(docs)
        self._collection.flush()

    def query(self, embedding, k=3, collections: Optional[List[str]] = None):
        _zvec = self._zvec
        results = self._collection.query(
            vectors=_zvec.VectorQuery("embedding", vector=embedding),
            topk=k,
            output_fields=["document", "source", "collection"],
        )
        ids = []
        documents = []
        distances = []
        for doc in results:
            # Filter by collection in Python if requested.
            if collections:
                doc_coll = doc.field("collection") or "default"
                if doc_coll not in collections:
                    continue
            ids.append(doc.id)
            documents.append(doc.field("document"))
            distances.append(-doc.score)  # negate: ChromaDB uses lower=better
        return {"ids": [ids], "documents": [documents], "distances": [distances]}

    def count(self):
        return self._collection.stats.doc_count

    def list_collections(self) -> List[Dict[str, object]]:
        """Return distinct collection names with document counts."""
        # zvec does not support metadata aggregation natively;
        # iterate all docs and count in Python.
        all_results = self._collection.query(
            vectors=None,
            topk=self.count() or 1,
            output_fields=["collection"],
        )
        counts: Dict[str, int] = {}
        for doc in all_results:
            name = doc.field("collection") or "default"
            counts[name] = counts.get(name, 0) + 1
        return [{"name": n, "doc_count": c} for n, c in sorted(counts.items())]


_BUILTIN_BACKENDS = {
    "chromadb": ChromaBackend,
    "zvec": ZvecBackend,
}


def get_backend(embedder):
    """Factory: return vector backend based on VECTOR_BACKEND env var.

    Special activation rules (checked before the VECTOR_BACKEND var):

    * ``ALCOVE_DEMO_ROOT`` set → ``MultiRootBackend`` (one ChromaDB client per
      subdirectory that contains a ``chroma/`` folder).
    * ``VECTOR_BACKEND=chromadb`` **and** (``CHROMA_COLLECTION=*`` or
      ``ALCOVE_MULTI_COLLECTION=1``) → ``MultiChromaBackend`` (fan-out across
      all named collections inside a single ChromaDB directory).
    """
    from alcove.plugins import discover_backends

    # Multi-root mode (separate ChromaDB per subdirectory) takes top priority
    if os.getenv("ALCOVE_DEMO_ROOT", ""):
        return MultiRootBackend(embedder)

    name = os.getenv("VECTOR_BACKEND", "chromadb").lower()
    backends = dict(_BUILTIN_BACKENDS)
    backends.update(discover_backends())
    cls = backends.get(name)
    if cls is None:
        raise ValueError(f"Unknown VECTOR_BACKEND: {name!r}")

    # Activate multi-collection mode for chromadb backend
    if name == "chromadb":
        multi = (
            os.getenv("CHROMA_COLLECTION", "") == "*"
            or os.getenv("ALCOVE_MULTI_COLLECTION", "").lower() in ("1", "true", "yes")
        )
        if multi:
            return MultiChromaBackend(embedder)

    return cls(embedder)
