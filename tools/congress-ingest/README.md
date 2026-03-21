# congress-ingest

Resumable GovInfo BillSum XML ingest into a local ChromaDB collection.

Downloads bill-summary ZIP bundles from [GovInfo](https://www.govinfo.gov/) (congresses 113–119),
parses each XML file, embeds summaries via a local Ollama model, and upserts them into a
persistent ChromaDB collection.

## Usage

```bash
# dry run — parse and count only, no embedding or storage
python tools/congress-ingest/ingest_bills.py --congress 118 --dry-run

# full ingest for a single congress
python tools/congress-ingest/ingest_bills.py --congress 118 \
    --chroma-path ./data/chroma \
    --ollama-url http://localhost:11434

# ingest all available congresses (113–119)
python tools/congress-ingest/ingest_bills.py --congress all --chroma-path ./data/chroma

# ingest from local XML files / ZIPs / directories
python tools/congress-ingest/ingest_bills.py \
    --source-path ./data/raw/BILLSUM-118hr.zip \
    --chroma-path ./data/chroma
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BILLSUM_CHROMA_PATH` | `./data/chroma` | Persistent ChromaDB path |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API base URL |

## Dependencies

```text
defusedxml
chromadb
```

The Ollama server must be running with an embedding-capable model loaded (e.g. `nomic-embed-text`).

## Output collection

ChromaDB collection `congress_summaries`. Each document is a single bill summary with metadata:
`congress`, `bill_type`, `bill_number`, `version_code`, `chamber`, `action_date`, `title`,
`is_latest`, `url`.
