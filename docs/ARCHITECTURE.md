# 🏗️ Architecture

## Pipeline (local-only default)

1. **📥 Ingest** — `alcove/ingest` discovers files in `data/raw/**` and extracts text using format-specific extractors, then chunks into JSONL.

2. **📊 Index** — `alcove/index` reads chunks and writes embeddings + metadata to a local vector store (ChromaDB by default).

3. **🔍 Query** — `alcove/query` retrieves results via CLI or a built-in FastAPI web service.

## Data flow

```
data/raw/*  →  data/processed/chunks.jsonl  →  vector store  →  query responses
```

## 📄 Supported formats

| Format | Extension | Dependency |
|--------|-----------|------------|
| Plain text | `.txt` | — |
| PDF | `.pdf` | pypdf |
| EPUB | `.epub` | ebooklib (optional) |
| HTML | `.html`, `.htm` | beautifulsoup4 |
| Markdown | `.md` | — |
| reStructuredText | `.rst` | — |
| CSV | `.csv` | — |
| TSV | `.tsv` | — |
| JSON | `.json` | — |
| JSONL | `.jsonl` | — |
| DOCX | `.docx` | python-docx (optional) |

## 🧠 Embedders

| Name | Env value | Description |
|------|-----------|-------------|
| Hash (default) | `EMBEDDER=hash` | Deterministic SHA-256 hash — offline, zero download, good for smoke tests |
| Sentence Transformers | `EMBEDDER=sentence-transformers` | Real semantic search via `all-MiniLM-L6-v2` (~80 MB model downloaded on first use) |

Set the embedder with the `EMBEDDER` environment variable. Third-party embedders can be installed as plugins (see below).

## 💾 Vector backends

| Name | Env value | Dependency |
|------|-----------|------------|
| ChromaDB (default) | `VECTOR_BACKEND=chromadb` | chromadb (included) |
| zvec | `VECTOR_BACKEND=zvec` | zvec (optional) |

Set the backend with the `VECTOR_BACKEND` environment variable.

## 🔌 Plugin system

Alcove discovers plugins via [Python entry points](https://packaging.python.org/en/latest/specifications/entry-points/). Three extension groups are available:

| Group | Purpose | Example entry point |
|-------|---------|---------------------|
| `alcove.extractors` | Add file format support | `rtf = my_plugin:extract_rtf` |
| `alcove.backends` | Add vector store backends | `pinecone = my_plugin:PineconeBackend` |
| `alcove.embedders` | Add embedding models | `openai = my_plugin:OpenAIEmbedder` |

To create a plugin, add an `[project.entry-points]` section in your package's `pyproject.toml`:

```toml
[project.entry-points."alcove.extractors"]
rtf = "my_plugin:extract_rtf"
```

Plugins are merged with builtins at runtime. Plugin extractors and backends take precedence over builtins with the same name.

## 🛡️ Boundary

- Operator owns host + storage
- No default outbound network calls (sentence-transformers downloads a model on first use only)
- Telemetry disabled by default

## ⚖️ Tradeoffs

- Hash embedder ships as default for zero-download offline use — swap to sentence-transformers for real semantic quality
- Thin implementation for speed-to-demo
- ChromaDB for broad compatibility; zvec for lighter footprint
