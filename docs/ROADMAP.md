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

## Out of scope

Alcove will not become a hosted service. There is no plan for cloud storage integrations, SaaS features, or a managed offering. The architecture assumes the operator owns the hardware. If that assumption does not hold, Alcove is the wrong tool.
