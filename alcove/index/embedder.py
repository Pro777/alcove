from __future__ import annotations

import hashlib
import os
from typing import List


class HashEmbedder:
    """Offline deterministic embedder for local smoke and private-first defaults."""

    def __init__(self, dim: int = 128):
        self.dim = dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vals = [(h[i % len(h)] / 255.0) for i in range(self.dim)]
            vectors.append(vals)
        return vectors


class SentenceTransformerEmbedder:
    """Semantic embedder using all-MiniLM-L6-v2. Downloads model on first use (~80MB)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def embed(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return [vec.tolist() for vec in embeddings]


def get_collection_name(base_name: str) -> str:
    """Append embedder-specific suffix to collection name."""
    embedder = os.getenv("EMBEDDER", "hash")
    if embedder == "sentence-transformers":
        return f"{base_name}_st"
    return base_name


_BUILTIN_EMBEDDERS = {
    "hash": HashEmbedder,
    "sentence-transformers": SentenceTransformerEmbedder,
}


def get_embedder():
    """Return embedder instance based on EMBEDDER env var."""
    from alcove.plugins import discover_embedders

    choice = os.getenv("EMBEDDER", "hash")
    embedders = dict(_BUILTIN_EMBEDDERS)
    embedders.update(discover_embedders())
    cls = embedders.get(choice)
    if cls is None:
        raise ValueError(f"Unknown embedder: {choice!r}.")
    return cls()
