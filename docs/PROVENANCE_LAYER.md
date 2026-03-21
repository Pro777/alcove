# Provenance Layer

Alcove is a view layer, not a copy layer. The design principle: store where data came from
alongside what it says. Every chunk in the vector index should be traceable back to its
source document, and every source document should be traceable to its origin.

---

## What provenance is

Provenance metadata answers three questions about a search result:

1. **Where did this come from?** (source URL, file path, or collection name)
2. **When was it collected?** (ingest date, publication date, update date)
3. **Who made it available?** (publisher, license, author)

This is distinct from ranking and relevance. A result can be highly relevant and have
unknown provenance — for many use cases that is acceptable. For archival, legal, or
compliance applications, known provenance is a hard requirement.

---

## How Alcove represents provenance

Every chunk stored in the vector index carries a `metadata` dict alongside its text
and embedding vector. The built-in fields that support provenance:

| Field | Type | Description |
|-------|------|-------------|
| `source` | string | Original file path or URL the chunk was extracted from |
| `collection` | string | ChromaDB collection name |
| `chunk_index` | int | Position of this chunk within the source document |
| `ingest_date` | string (ISO 8601) | Date the chunk was written to the index |

These fields are written by the ingest pipeline automatically when a file is processed.
Additional fields (e.g. `title`, `author`, `license`, `url`) can be added by the
extractor or by a custom ingest script.

---

## Manifest-based provenance

The `alcove.schema.json` manifest documents each collection at the collection level. An
entry in the manifest looks like:

```json
{
  "collection": "congress_summaries",
  "source": "GovInfo BILLSUM XML bundles",
  "source_url": "https://www.govinfo.gov/bulkdata/BILLSUM/",
  "license": "Public domain (U.S. government works, 17 U.S.C. § 105)",
  "ingest_date": "2025-11-01",
  "chunk_count": 48291,
  "description": "Bill summaries for the 113th–119th U.S. Congress"
}
```

The manifest lives at `docs/alcove.schema.json` and is updated after each ingest run.
It is the authoritative record of what is in the index and where it came from.

---

## Adding provenance to a custom ingest script

When writing a custom ingest script, pass provenance fields in the metadata dict:

```python
chunks = [
    {
        "id": "my-collection-doc-0001-chunk-00",
        "document": "The text of the chunk...",
        "metadata": {
            "source": "https://example.com/document.pdf",
            "title": "Annual Report 2024",
            "author": "Jane Smith",
            "license": "CC BY 4.0",
            "ingest_date": "2025-01-15",
            "collection": "my-collection",
            "chunk_index": 0,
        },
    },
    ...
]
collection.upsert(
    ids=[c["id"] for c in chunks],
    documents=[c["document"] for c in chunks],
    metadatas=[c["metadata"] for c in chunks],
    embeddings=embedder.embed_documents([c["document"] for c in chunks]),
)
```

---

## Provenance in search results

The Alcove query API returns the full metadata dict with each result. The web UI
renders `source` and `url` as links when present. A result card without a source URL
displays the file path as plain text.

Custom result rendering can add provenance display by overriding the `result_card`
block in `alcove/web/templates/results.html`.

---

## Licensing and compliance

Provenance metadata does not enforce license compliance — it surfaces the information
needed for a human to make compliance decisions. The recommended pattern:

1. Record `license` in metadata at ingest time.
2. Include `license` in the visible result card for corpora with attribution requirements.
3. Keep a `source_url` pointing to the canonical upstream copy so results can be
   verified against the original.

For corpora with strict attribution requirements (e.g., Creative Commons BY),
displaying the `author` and `source_url` in the UI satisfies the typical requirement.

---

## See also

- [ARCHITECTURE.md](ARCHITECTURE.md) — ingest/index pipeline overview
- [MANIFEST.md](MANIFEST.md) — corpus manifest format and update instructions
- [docs/alcove.schema.json](alcove.schema.json) — live manifest
