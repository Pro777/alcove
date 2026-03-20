# Embedder & Backend Alternatives

Alcove ships with defaults that work for general-purpose corpora. If your corpus is domain-specific, or if you need different performance characteristics, swap the embedder or vector backend.

## Domain Embedders

Swap the default embedder for better in-domain retrieval. Configure in `alcove.toml` under `[embedder]`.

| Embedder | Best for |
|----------|----------|
| [`legal-bert`](https://huggingface.co/nlpaueb/legal-bert-base-uncased) | Legal documents, case law, contracts |
| [`specter2`](https://huggingface.co/allenai/specter2) ([AllenAI](https://allenai.org)) | Scientific papers, citations, abstracts |
| [`BiomedNLP-BiomedBERT`](https://huggingface.co/microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext) | Biomedical literature, clinical notes |
| [`mlx-lm`](https://github.com/ml-explore/mlx-lm) (Apple Silicon) | On-device throughput on M-series Macs |

Domain embedders matter when your corpus vocabulary is specialized. General-purpose models handle everyday language well, but they may not have seen enough domain text to produce useful embeddings for legal terms, scientific nomenclature, or medical language. If retrieval quality seems low on a specialized corpus, the embedder is the first thing to check.

## Vector Backends

[ChromaDB](https://trychroma.com) is the default. It works well for single-machine deployments up to a few million chunks. If you need different trade-offs, these are the tested alternatives.

| Backend | Library | When to use it |
|---------|---------|----------------|
| SQLite-vec | [`sqlite-vec`](https://github.com/asg017/sqlite-vec) | Single-file index. Copy the `.db`, move the index. Zero external process. Good for small corpora and air-gapped deployments. |
| Qdrant | [`qdrant-client`](https://github.com/qdrant/qdrant-client) | Lighter memory footprint at scale. Built-in sparse vector support for hybrid BM25+vector retrieval. |
| Weaviate | [`weaviate-client`](https://github.com/weaviate/weaviate-python-client) | Native BM25+vector hybrid. Strong metadata filter API. Good when your queries rely heavily on structured filters alongside semantic search. |

### Choosing a Backend

Start with the default (ChromaDB) unless you have a specific reason to switch. The main reasons to change:

- **Portability:** SQLite-vec produces a single file you can copy, archive, or move between machines.
- **Scale:** Qdrant and Weaviate handle larger corpora with lower memory pressure.
- **Hybrid retrieval:** If your queries mix keyword and semantic search heavily, Qdrant or Weaviate give you built-in BM25 without extra configuration.

Backend configuration lives in `alcove.toml` under `[vector_store]`. Changing the backend after ingest requires re-indexing.
