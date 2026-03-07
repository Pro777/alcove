"""Keyword search via BM25 scoring over stored document chunks."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class KeywordIndex:
    """BM25-based keyword search over a chunks.jsonl file.

    Lazily loads and tokenizes chunks on first search call.
    Returns results in the same shape as backend.query() for
    easy interoperability with the semantic pipeline.
    """

    def __init__(self, chunks_file: Optional[str] = None):
        self._chunks_file = chunks_file or os.getenv(
            "CHUNKS_FILE", "data/processed/chunks.jsonl"
        )
        self._bm25 = None
        self._chunks: List[Dict] = []

    def _load(self):
        """Read chunks.jsonl, tokenize, and build BM25 index."""
        from rank_bm25 import BM25Okapi

        path = Path(self._chunks_file)
        self._chunks = []
        tokenized: List[List[str]] = []

        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    text = rec.get("text", "")
                    self._chunks.append({
                        "id": rec.get("id", ""),
                        "text": text,
                        "source": rec.get("source", ""),
                    })
                    tokenized.append(text.lower().split())

        if tokenized:
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._bm25 = None

    def search(self, query: str, k: int = 3) -> dict:
        """Search the keyword index for the given query.

        Returns results in ChromaDB-compatible format:
        {"ids": [[...]], "documents": [[...]], "distances": [[...]]}

        Distances are computed as 1.0 - normalized_score so that
        lower values indicate better matches (matching ChromaDB convention).
        """
        if self._bm25 is None:
            self._load()

        # Empty index: return empty results
        if self._bm25 is None or not self._chunks:
            return {"ids": [[]], "documents": [[]], "distances": [[]]}

        query_tokens = query.lower().split()
        if not query_tokens:
            return {"ids": [[]], "documents": [[]], "distances": [[]]}

        scores = self._bm25.get_scores(query_tokens)

        max_score = float(max(scores)) if len(scores) > 0 else 0.0

        # Build scored list of (index, normalized_score)
        scored = []
        for idx, raw_score in enumerate(scores):
            if max_score > 0:
                norm = float(raw_score) / max_score
            else:
                norm = 0.0
            scored.append((idx, norm))

        # Sort by normalized score descending, take top-k
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:k]

        ids: List[str] = []
        documents: List[str] = []
        distances: List[float] = []

        for idx, norm in top:
            chunk = self._chunks[idx]
            ids.append(chunk["id"])
            documents.append(chunk["text"])
            distances.append(round(1.0 - norm, 6))

        return {"ids": [ids], "documents": [documents], "distances": [distances]}
