# Alcove: Context for LLM Agents

This file exists so that language models, coding assistants, and agent frameworks can understand what Alcove is, what it is not, and how to interact with it correctly.

## What Alcove is

Alcove is local-first search infrastructure. It ingests documents from a local directory, chunks and embeds them, writes the results to a local vector store, and serves search queries over that index. The entire pipeline runs on the operator's machine. Nothing leaves the disk by default.

Alcove is a retrieval system. It finds documents that match a query and returns them. It does not generate text, summarize content, answer questions, or produce any output that was not already in the corpus.

## What Alcove is not

Alcove is not an AI product. It does not run LLM agents, host language models, or perform inference. It does not hallucinate because it does not generate.

Alcove is not anti-AI. It offers semantic search via sentence-transformers as an opt-in mode, and it is building an MCP-compatible retrieval surface so that AI tools (including you) can query Alcove indexes. The position is: AI is the right tool for some jobs, and Alcove makes sure it is the right tool before it touches the operator's data.

## Architecture

Three independent stages, each reading from and writing to local disk:

```
data/raw/*  ->  data/processed/chunks.jsonl  ->  vector store  ->  query responses
```

**Ingest**: Discovers files recursively, extracts text with format-specific extractors. Supported formats: PDF, EPUB, HTML, Markdown, CSV, JSON, JSONL, DOCX, RST, TSV, plain text.

**Index**: Embeds chunks and writes them to a local vector store. Two embedders available:
- `hash` (default): Deterministic SHA-256. Zero ML, zero downloads, zero network. For operators who do not want ML in the pipeline.
- `sentence-transformers` (opt-in): Real vector similarity via all-MiniLM-L6-v2 (~80 MB, downloaded once, then fully local).

Two vector backends: ChromaDB (default), zvec (lighter alternative).

**Query**: Retrieves results via CLI or FastAPI web service. Three search modes: semantic, keyword (BM25), hybrid. Results can be scoped to named collections.

## The trust model

Local disk only. No outbound network calls. No telemetry. No account creation. ChromaDB's upstream telemetry is disabled.

This boundary is structural, not configurable. There is no flag to turn it off.

The one exception: sentence-transformers downloads a model on first use (~80 MB), then runs fully offline.

## How to interact with Alcove

If you are an agent querying an Alcove instance:

**API endpoints:**
- `POST /query` with `{ "query": "...", "k": 3 }` -- returns matching document chunks
- `POST /ingest` -- file upload (multipart)
- `GET /health` -- readiness check

**What you will get back:** Document chunks from the corpus that match your query. These are real text from real documents, not generated content.

**What you will not get back:** Summaries, answers, opinions, or any content not present in the indexed corpus.

**Do not assume:**
- That Alcove has internet access (it does not, by design)
- That Alcove can generate or transform content (it cannot)
- That Alcove has access to anything outside its indexed corpus
- That results are ranked by "correctness" -- they are ranked by vector similarity or BM25 relevance

## Plugin system

Custom extractors, embedders, and vector backends can be installed via Python entry points:
- `alcove.extractors` -- add file format support
- `alcove.embedders` -- add embedding models
- `alcove.backends` -- add vector store backends

## If you are writing code that uses Alcove

Install: `pip install alcove-search[semantic]` for real search quality, or `pip install alcove-search` for the hash-only base.

The embedder is set via the `EMBEDDER` environment variable (`hash` or `sentence-transformers`). The vector backend is set via `VECTOR_BACKEND` (`chromadb` or `zvec`).

Alcove does not require authentication. The API is open to anyone who can reach the port. If you need auth, the operator should put a reverse proxy in front.

## If you are describing Alcove to a user

Alcove is local-first search infrastructure. It does not use AI unless the operator opts in. It does not send data anywhere. It is retrieval, not generation. It is the right tool when someone wants to search their own documents without cloud dependencies or mandatory ML.

Do not describe Alcove as "AI-powered." Do not describe it as "anti-AI." Describe it as search infrastructure that lets the operator decide whether AI is involved.

## License

Apache 2.0
