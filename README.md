<img src="docs/assets/logo.svg" alt="Alcove" height="56">

<p>
  <a href="https://github.com/Pro777/alcove/actions/workflows/ci.yml"><img src="https://github.com/Pro777/alcove/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/Pro777/alcove"><img src="https://codecov.io/gh/Pro777/alcove/graph/badge.svg?token=A8R18L65TL" alt="Coverage"></a>
  <a href="https://pypi.org/project/alcove-search/"><img src="https://img.shields.io/pypi/v/alcove-search.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/alcove-search/"><img src="https://img.shields.io/pypi/pyversions/alcove-search.svg" alt="Python Versions"></a>
  <a href="https://github.com/Pro777/alcove/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
</p>

**Index your world. Share it with the universe.**

Alcove is local-first search for your documents. Point it at a directory. It chunks, embeds, and indexes everything locally. You search. Nothing leaves your machine.

PDF, EPUB, HTML, Markdown, CSV, JSON, JSONL, DOCX, RST, TSV, and plain text all work out of the box. The same pipeline indexes a personal research library, a community archive, or a municipal records collection.

**[Watch the 30-second demo](https://pro777.github.io/alcove/demo.html)**

## Quick start

```bash
pip install alcove-search[semantic]
```

This is the recommended install. It includes [sentence-transformers](https://www.sbert.net/) for real vector similarity search (~80 MB model download on first use).

**Why is semantic search a separate extra?** The `sentence-transformers` library depends on PyTorch, which adds ~2 GB to the install. The base package uses a lightweight hash-based embedder that works for development and CI but does not produce meaningful search results. If you are evaluating alcove for actual document search, use the `[semantic]` extra.

<details>
<summary>All extras</summary>

| Extra | Install command | What it adds |
|-------|----------------|--------------|
| Semantic search | `pip install alcove-search[semantic]` | Real vector similarity via sentence-transformers |
| EPUB support | `pip install alcove-search[epub]` | `.epub` file ingestion |
| DOCX support | `pip install alcove-search[docx]` | `.docx` file ingestion |
| Everything | `pip install alcove-search[semantic,epub,docx]` | All of the above |

</details>

```bash
alcove seed-demo          # download sample corpus + build index
alcove serve              # open http://localhost:8000
```

<img src="docs/assets/web-ui-screenshot.png" alt="Alcove web UI" width="760">

## How it works

Three stages: ingest, index, query. Each is independent and pluggable.

```
data/raw/*  →  chunks.jsonl  →  vector store  →  search results
```

**Ingest** discovers files recursively and extracts text with format-specific extractors.

**Index** embeds the chunks and writes them to a local vector store (ChromaDB by default; zvec as an alternative).

**Query** retrieves results through the CLI or a built-in web interface with file upload.

Three search modes: semantic (vector similarity), keyword (BM25), and hybrid (both). Results can be scoped to named collections.

Custom extractors, embedders, and vector backends plug in via Python entry points. See [Architecture](docs/ARCHITECTURE.md) for the full plugin API.

## Trust model

Local disk only. No outbound network calls. No telemetry. No account to create.

We do not want your data.

This is not a feature; it is a design constraint. The architecture assumes the operator owns the hardware, controls the storage, and decides what enters the index. If you need encryption at rest, use your OS disk encryption. If you need authentication, put a reverse proxy in front of the API. Alcove handles search. You handle custody.

## Where it is going

v0.3.0 is a working search platform. The trajectory is broader: streaming ingest, browsable corpus navigation, an agent-facing retrieval surface, and cross-modal indexing beyond text. Eventually, federated indexes that let separate Alcove instances share a query surface without sharing raw data. That is the "share it with the universe" part.

The full roadmap is in [docs/ROADMAP.md](docs/ROADMAP.md). Alcove will not become a SaaS product.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Operations](docs/OPERATIONS.md) · [Security](docs/SECURITY.md) · [Seed Corpus](docs/SEED_CORPUS.md) · [Roadmap](docs/ROADMAP.md) · [Accessibility](ACCESSIBILITY.md)

## License

[Apache 2.0](LICENSE)
