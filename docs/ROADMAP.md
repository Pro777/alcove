# Roadmap

## Current release (v0.3.0)

Alcove ships a working three-stage pipeline: ingest, index, query. Eleven document formats. Two embedders (hash for offline determinism, sentence-transformers for real semantic search). Two vector backends (ChromaDB, zvec). A plugin system.

A web UI with upload and search. CI across Python 3.10, 3.11, 3.12. Docker deployment. Apache 2.0.

This is the foundation. Everything below builds on it.

## Near-term

**More formats.** RTF, ODT, PPTX, XLSX. The [extractor plugin API](ARCHITECTURE.md#plugin-system) already supports this; the work is writing and testing each one.

**Semantic search as default.** The hash embedder exists for zero-download offline bootstrapping and for operators who do not want ML in the pipeline. Once the onboarding experience is smooth enough, sentence-transformers (or a lighter alternative) becomes the default install. The hash embedder stays available: not a stepping stone, but a permanent option for people who want deterministic, inspectable results.

**Browse mode.** Alcove should be navigable, not just searchable. Directory-aware corpus browsing in the web UI: see what you have, not just what matches a query. Search and browse are complementary interfaces to the same index.

**MCP endpoint.** This is the "share it with the universe" part. An MCP-compatible retrieval surface that lets Claude, ChatGPT, a public-facing website, or any other tool query your index. Your corpus stays local. Your index stays yours. The answers are available to whoever you choose to expose them to. Because Alcove is retrieval, not generation, those answers are what your documents actually say: no hallucinations, no editorializing, no slop. Alcove already runs a local API; exposing it as an MCP tool server is a natural extension. [MCP changes the security surface](SECURITY.md#security-model); review it before exposing the endpoint. Context7 compatibility is a goal.

**Streaming ingest.** Watch a directory and re-index on change. The current pipeline is batch-oriented: you run `alcove ingest`, it processes everything. Streaming mode keeps the index current without manual intervention.

## Mid-term

**Cross-modal indexing.** Audio transcription, image OCR, video keyframe extraction. The pipeline architecture already separates extraction from embedding; new modalities plug in as extractors that produce text chunks from non-text sources. Bioacoustics and field recordings are a motivating use case, not an afterthought.

**Relevance as memory, not just distance.** Vector similarity is a starting point. A more useful index would treat recency, frequency of access, and familiarity as first-class relevance signals: things you work with often should surface faster; things you have not touched in years should fade gracefully. This is the Dreyfus-inspired layer: an index that behaves more like memory than search.

**Richer plugin API.** Lifecycle hooks, query-time transformations, custom ranking. The current plugin surface covers extractors, embedders, and backends. Mid-term work expands it to cover more of the pipeline.

## Long-term

**Federation.** Multiple Alcove instances sharing a query surface without sharing raw data. A research group, a neighborhood archive, a distributed records system: each node owns its corpus, but queries can span the constellation. [Sovereignty is preserved; reach is expanded.](../WHY.md#the-tension-is-the-product)

**Desktop application.** A native app for people who should not need a terminal to search their own files. This is packaging and distribution work, not architecture work; the core stays the same.

## Plugin candidates

The [plugin API](ARCHITECTURE.md#plugin-system) exposes three extension points: extractors (`alcove.extractors`), vector backends (`alcove.backends`), and embedders (`alcove.embedders`). Below are concrete candidates for each, with the libraries that would implement them and how they wire into the pipeline.

**Offline by default.** Alcove makes no outbound network calls unless the operator explicitly selects a cloud plugin. All built-in extractors, embedders, and backends run entirely on the operator's hardware. Selecting a cloud embedder (OpenAI, Cohere) or a cloud backend (Pinecone) changes that: data leaves the machine. This is an operator decision, not a default. Each cloud candidate in the tables below calls this out explicitly.

### Extractor plugins

Extractors receive a file path and return a list of text chunks. The entry point maps a file extension to a callable: `rtf = my_plugin:extract_rtf`. Plugins override built-ins on name collision.

| Candidate | Library | Wiring |
|-----------|---------|--------|
| RTF | `striprtf` | `ep.name = "rtf"`, callable strips RTF markup → plain text, chunked by paragraph |
| ODT / ODP / ODS | `odfpy` | `ep.name = "odt"` etc.; parse ODF XML, extract text nodes, chunk by heading or paragraph |
| PPTX | `python-pptx` | `ep.name = "pptx"`; iterate slides, pull `shape.text_frame.text`, one chunk per slide |
| XLSX | `openpyxl` | `ep.name = "xlsx"`; iterate sheets and rows, emit one chunk per sheet (column headers + row values as prose) |
| HTML | `beautifulsoup4` | `ep.name = "html"`; strip tags, extract visible text, chunk by block element |
| Audio transcription | `faster-whisper` | `ep.name = "mp3"` / `"wav"` / `"m4a"`; transcribe via local Whisper model, emit time-coded text chunks |
| Image (vision) | `ollama` + LLaVA | `ep.name = "png"` / `"jpg"`; send image to local vision model, return description as a single chunk |
| Markdown | `markdown` / `mistletoe` | `ep.name = "md"`; parse AST, chunk by heading level |

### Embedder plugins

Embedders receive a list of strings and return a list of float vectors. They register on the `alcove.embedders` group and are selected via the `EMBEDDER` env var.

| Candidate | Library | Wiring |
|-----------|---------|--------|
| OpenAI | `openai` | Calls `client.embeddings.create(model="text-embedding-3-small", input=texts)`; requires `OPENAI_API_KEY`. Breaks local-only boundary — document this clearly. |
| Ollama | `ollama` | Calls local `ollama.embeddings(model=..., prompt=text)` per chunk; model configured via env var. Zero-download after first pull. |
| MLX (Apple Silicon) | `mlx-lm` | Runs embedding model via MLX on M-series GPU; fastest local option for Apple hardware. |
| Cohere | `cohere` | Calls `co.embed(texts=..., model=...)` via Cohere API; requires API key. Cloud boundary applies. |

### Backend plugins

Backends store and query embedded chunks. They register on the `alcove.backends` group and expose a class that inherits from `VectorBackend`. Selected via `VECTOR_BACKEND` env var.

| Candidate | Library | Wiring |
|-----------|---------|--------|
| Qdrant | `qdrant-client` | `QdrantBackend` wraps `QdrantClient`; supports local file mode and remote server. Lighter than ChromaDB for large corpora. |
| Weaviate | `weaviate-client` | `WeaviateBackend` wraps v4 client; hybrid BM25 + vector search built in. |
| Pinecone | `pinecone` | `PineconeBackend` is cloud-only; breaks local-first posture. Useful for operators who need managed scale — document the tradeoff. |
| SQLite-vec | `sqlite-vec` | Embeds vector search directly in a SQLite file; zero external dependencies, single-file corpus portability. Strong fit for the desktop app goal. |

### Plugin interface contract

All three extension points use Python entry points — no framework dependency, no runtime coupling. The contract per type:

- **Extractor**: `(path: str | Path) -> list[str]` — return plain-text chunks. Raise on unreadable files.
- **Embedder**: class with `embed(texts: list[str]) -> list[list[float]]` — must be deterministic per input if possible; document non-determinism.
- **Backend**: class with `add(chunks, embeddings, metadatas)`, `query(embedding, k, **filters) -> list[dict]`, `count() -> int`. Match the existing `VectorBackend` ABC in `alcove/index/backend.py`.

**Authentication is out of scope for the plugin system.** The plugin interfaces handle data flow only — extraction, embedding, storage. They provide no authentication mechanism and make no trust decisions. When exposing Alcove endpoints (e.g., the local API or a future MCP surface), authentication must be enforced at the deployment boundary: a reverse proxy, network policy, or OS-level access control. This applies to all three extension types; no plugin implementation should assume the caller is authenticated.

Mid-term roadmap work (lifecycle hooks, query-time transformations) will expand this surface. New groups will follow the same entry-point pattern.

## Out of scope

Alcove will not become a hosted service. There is no plan for cloud storage integrations, SaaS features, or a managed offering. The architecture assumes the operator owns the hardware. If that assumption does not hold, Alcove is the wrong tool.
