from __future__ import annotations

import os
from typing import Dict, List, Optional

import chromadb
from chromadb.config import Settings

from .embedder import get_collection_name


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
    """Factory: return vector backend based on VECTOR_BACKEND env var."""
    from alcove.plugins import discover_backends

    name = os.getenv("VECTOR_BACKEND", "chromadb").lower()
    backends = dict(_BUILTIN_BACKENDS)
    backends.update(discover_backends())
    cls = backends.get(name)
    if cls is None:
        raise ValueError(f"Unknown VECTOR_BACKEND: {name!r}")
    return cls(embedder)
