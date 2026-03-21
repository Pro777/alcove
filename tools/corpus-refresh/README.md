# corpus-refresh

Incremental ingest runner for arXiv and PsyArXiv collections.

Queries the arXiv and/or PsyArXiv APIs for papers updated since the last
checkpoint, downloads their metadata, and upserts them into a local Alcove
ChromaDB collection. Designed to run on a schedule (e.g. daily via cron or
launchd) to keep collections fresh without re-processing the entire corpus.

## Usage

```bash
# Refresh arXiv cs.AI papers updated in the last 7 days
python tools/corpus-refresh/refresh.py arxiv \
    --query "cat:cs.AI" --days 7 --chroma-path ./data/chroma

# Refresh all PsyArXiv preprints from the last 14 days
python tools/corpus-refresh/refresh.py psyarxiv \
    --days 14 --chroma-path ./data/chroma

# Dry run — show counts without writing
python tools/corpus-refresh/refresh.py --dry-run arxiv --query "cat:cs.AI"
```

## Requirements

- `defusedxml` — safe XML parsing for arXiv Atom feeds
- `chromadb` — for writing to the collection

Install:
```bash
pip install defusedxml chromadb
```

## Checkpoint

Successful runs save a timestamp to `<chroma-path>/../corpus_refresh_checkpoint.json`
(or `--checkpoint-path`). On the next run, only papers updated after that
timestamp are fetched. This makes runs fast and idempotent.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CORPUS_CHROMA_PATH` | `./data/chroma` | ChromaDB persistent path |
| `ARXIV_COLLECTION` | `arxiv` | ChromaDB collection name for arXiv |
| `PSYARXIV_COLLECTION` | `psyarxiv` | ChromaDB collection name for PsyArXiv |
