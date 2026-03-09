# Architecture

Three stages: ingest, index, query. They are independent modules that operate over local files only. Each stage reads from disk, writes to disk, and knows nothing about the others. You can re-run any stage without touching the rest.

```
data/raw/*  ->  data/processed/chunks.jsonl  ->  vector store  ->  query responses
```

## Ingest

`alcove/ingest` discovers files in `data/raw/**` and extracts text using format-specific extractors, then chunks the output into JSONL.

## Index

`alcove/index` reads chunks and writes embeddings plus metadata to a local vector store. ChromaDB is the default. zvec is the alternative.

## Query

`alcove/query` retrieves results via the CLI or a built-in FastAPI web service with file upload.

## Supported formats

| Format | Extension | Dependency |
|--------|-----------|------------|
| Plain text | `.txt` | none |
| PDF | `.pdf` | pypdf |
| EPUB | `.epub` | ebooklib (optional) |
| HTML | `.html`, `.htm` | beautifulsoup4 |
| Markdown | `.md` | none |
| reStructuredText | `.rst` | none |
| CSV | `.csv` | none |
| TSV | `.tsv` | none |
| JSON | `.json` | none |
| JSONL | `.jsonl` | none |
| DOCX | `.docx` | python-docx (optional) |

## Embedders

The two embedders are not a feature tier. They are a trust decision.

| Name | Env value | What it means |
|------|-----------|---------------|
| Hash (default) | `EMBEDDER=hash` | Deterministic SHA-256. Zero ML, zero model downloads, zero network. Every output is a pure function of the input. For operators who do not want machine learning in their pipeline at all. Also useful for CI and airgapped environments. |
| Sentence Transformers | `EMBEDDER=sentence-transformers` | Real semantic search via `all-MiniLM-L6-v2` (~80 MB model, downloaded on first use, then fully local). For operators who want vector similarity without cloud dependency. This is retrieval, not generation. |

Set the embedder with the `EMBEDDER` environment variable. Custom embedders can be installed as plugins.

## Vector backends

| Name | Env value | Dependency |
|------|-----------|------------|
| ChromaDB (default) | `VECTOR_BACKEND=chromadb` | chromadb (included) |
| zvec | `VECTOR_BACKEND=zvec` | zvec (optional) |

Set the backend with the `VECTOR_BACKEND` environment variable.

## Plugin system

Custom extractors, embedders, and vector backends plug in via [Python entry points](https://packaging.python.org/en/latest/specifications/entry-points/). Three extension groups:

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

Plugins are merged with builtins at startup. When a plugin and a builtin share the same name, the plugin wins.

## Boundary

The operator owns the host and the storage. Alcove makes no outbound network calls by default; the one exception is `sentence-transformers`, which downloads a model on first use and then runs locally. Telemetry is disabled, including ChromaDB's upstream telemetry.

This boundary is structural, not configurable. There is no flag to turn it off because there is nothing to turn off.

## Tradeoffs

The hash embedder ships as the default because it requires zero downloads, works offline, and imposes no ML dependency on operators who did not ask for one. The cost is that it produces deterministic but non-semantic vectors; swap to `sentence-transformers` for real search quality.

ChromaDB is the default backend for broad compatibility and ecosystem support. zvec is available for deployments where a lighter footprint matters more than ChromaDB's feature set.

The implementation is deliberately thin. The goal at v0.3.0 is a correct, working pipeline, not an optimized one. Performance work comes after the architecture is proven.
