# Operations

## First run

```bash
pip install alcove-search
alcove seed-demo          # download sample corpus + build index
alcove serve              # open http://localhost:8000
```

## Enabling semantic search

By default, Alcove uses a deterministic hash embedder (offline, zero download). For real semantic search:

```bash
pip install alcove-search[semantic]
EMBEDDER=sentence-transformers alcove seed-demo
EMBEDDER=sentence-transformers alcove serve
```

This downloads `all-MiniLM-L6-v2` (~80 MB) on first use. The model is cached locally; subsequent runs are offline.

## Custom documents

```bash
alcove ingest /path/to/your/files
alcove serve
```

Files can also be uploaded through the web UI at `http://localhost:8000`.

## Web UI and API

```bash
alcove serve
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI (search and file upload) |
| `/query` | POST | `{ "query": "...", "k": 3 }` |
| `/ingest` | POST | File upload (multipart) |
| `/health` | GET | Readiness check |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDER` | `hash` | Embedder to use (`hash` or `sentence-transformers`) |
| `VECTOR_BACKEND` | `chromadb` | Vector store (`chromadb` or `zvec`) |
| `CHROMA_PATH` | `./data/chroma` | ChromaDB persistence directory |
| `CHROMA_COLLECTION` | `alcove_docs` | Collection name |
| `CHUNK_SIZE` | `1000` | Characters per chunk |
| `CHUNK_OVERLAP` | `150` | Overlap between chunks |
| `RAW_DIR` | `data/raw` | Input directory for ingestion |

## Docker

```bash
docker compose up -d --build
```

The container exposes port 8000 and includes a `/health` endpoint for readiness checks.

## Backup

Back up `data/raw`, `data/processed`, and `data/chroma` (or `data/zvec` if using the zvec backend). These directories contain everything Alcove needs to reconstruct the index.

## Running tests

```bash
pip install alcove-search[dev]
pytest
```
