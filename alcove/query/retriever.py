from __future__ import annotations

from typing import Dict, List, Optional

from alcove.index.backend import get_backend
from alcove.index.embedder import get_embedder


def query_text(q: str, n_results: int = 3, collections: Optional[List[str]] = None):
    embedder = get_embedder()
    backend = get_backend(embedder)
    emb = embedder.embed([q])[0]
    return backend.query(emb, k=n_results, collections=collections)


def query_keyword(q: str, n_results: int = 3) -> dict:
    """Run a keyword (BM25) search over the chunks index."""
    from alcove.index.keyword import KeywordIndex
    idx = KeywordIndex()
    return idx.search(q, k=n_results)


def query_hybrid(
    q: str,
    n_results: int = 3,
    collections: Optional[List[str]] = None,
) -> dict:
    """Run both semantic and keyword search, merge by averaging scores.

    Deduplicates by document id. Returns top-k results sorted by
    combined score (lower distance = better match).
    """
    semantic = query_text(q, n_results=n_results, collections=collections)
    keyword = query_keyword(q, n_results=n_results)

    # Collect per-id scores from both result sets.
    merged: Dict[str, dict] = {}

    sem_ids = semantic.get("ids", [[]])[0]
    sem_docs = semantic.get("documents", [[]])[0]
    sem_dists = semantic.get("distances", [[]])[0]

    for doc_id, doc, dist in zip(sem_ids, sem_docs, sem_dists):
        merged[doc_id] = {
            "document": doc,
            "sem_dist": float(dist),
            "kw_dist": None,
        }

    kw_ids = keyword.get("ids", [[]])[0]
    kw_docs = keyword.get("documents", [[]])[0]
    kw_dists = keyword.get("distances", [[]])[0]

    for doc_id, doc, dist in zip(kw_ids, kw_docs, kw_dists):
        if doc_id in merged:
            merged[doc_id]["kw_dist"] = float(dist)
        else:
            merged[doc_id] = {
                "document": doc,
                "sem_dist": None,
                "kw_dist": float(dist),
            }

    # Compute average distance. When a source is missing, treat as 1.0 (worst).
    scored = []
    for doc_id, info in merged.items():
        sem_d = info["sem_dist"] if info["sem_dist"] is not None else 1.0
        kw_d = info["kw_dist"] if info["kw_dist"] is not None else 1.0
        avg_dist = (sem_d + kw_d) / 2.0
        scored.append((doc_id, info["document"], avg_dist))

    scored.sort(key=lambda x: x[2])
    top = scored[:n_results]

    ids = [s[0] for s in top]
    documents = [s[1] for s in top]
    distances = [round(s[2], 6) for s in top]

    return {"ids": [ids], "documents": [documents], "distances": [distances]}
