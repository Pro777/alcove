# âš™ï¸ Operations

## ðŸš€ First run

```bash
pip install alcove-search
alcove seed-demo          # download sample corpus + build index
alcove serve              # open http://localhost:8000
```

## ðŸ§  Enabling semantic search

By default, Alcove uses a deterministic hash embedder (offline, zero download). For real semantic search:

```bash
pip install alcove-search[semantic]
EMBEDDER=sentence-transformers alcove seed-demo
EMBEDDER=sentence-transformers alcove serve
```

This downloads `all-MiniLM-L6-v2` (~80 MB) on first use. The model is cached locally â€” subsequent runs are offline.

## ðŸ“‚ Custom documents

```bash
alcove ingest /path/to/your/files
alcove serve
```

Or use the web UI to upload files directly at `http://localhost:8000`.

## Regulatory corpus pilot

```bash
alcove mirrulations-demo data/raw/mirrulations --agency EPA --collection mirrulations_docs
alcove search "power plant emissions limits" --collection mirrulations_docs
```

See [Mirrulations Corpus](MIRRULATIONS_CORPUS.md) for the recommended text-only subset and sync pattern.

## ðŸŒ Web UI + API

```bash
alcove serve
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI (search + file upload) |
| `/query` | POST | `{ "query": "...", "k": 3 }` |
| `/ingest` | POST | File upload (multipart) |
| `/health` | GET | Readiness check |

## ðŸ”§ Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDER` | `hash` | Embedder to use (`hash` or `sentence-transformers`) |
| `VECTOR_BACKEND` | `chromadb` | Vector store (`chromadb` or `zvec`) |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB persistence directory |
| `CHROMA_COLLECTION` | `alcove_docs` | Collection name |
| `CHUNK_SIZE` | `1000` | Characters per chunk |
| `CHUNK_OVERLAP` | `150` | Overlap between chunks |
| `RAW_DIR` | `data/raw` | Input directory for ingestion |

## ðŸ³ Docker (optional)

```bash
docker compose up -d --build
```

## ðŸ’¾ Backup

Back up `data/raw`, `data/processed`, and `data/chroma` (or `data/zvec` if using the zvec backend).

## ðŸ§ª Running tests

```bash
pip install alcove-search[dev]
pytest
```
