from __future__ import annotations

import json
import os
from pathlib import Path

from .backend import get_backend
from .embedder import get_embedder


def run(chunks_file: str | None = None, collection: str = "default") -> int:
    chunks_file = chunks_file or os.getenv("CHUNKS_FILE", "data/processed/chunks.jsonl")

    embedder = get_embedder()
    backend = get_backend(embedder)

    ids, docs, metas = [], [], []
    with Path(chunks_file).open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ids.append(rec["id"])
            docs.append(rec["chunk"])
            metas.append({"source": rec["source"], "collection": collection})

    if not ids:
        return 0

    embeddings = embedder.embed(docs)
    backend.add(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
    return len(ids)


if __name__ == "__main__":
    n = run()
    print(f"indexed {n} chunks")
