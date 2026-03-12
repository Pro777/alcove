from __future__ import annotations

from alcove.index.backend import get_backend
from alcove.index.embedder import get_embedder


def query_text(q: str, n_results: int = 3, collection_name: str | None = None):
    embedder = get_embedder()
    backend = get_backend(embedder, collection_name=collection_name)
    emb = embedder.embed([q])[0]
    return backend.query(emb, k=n_results)
