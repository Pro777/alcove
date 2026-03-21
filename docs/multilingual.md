# Multilingual Support

Alcove supports multilingual and cross-lingual search out of the box when a multilingual
embedding model is configured. No per-language tokenizers, stop-word lists, or query
parsers are required.

---

## How it works

Alcove delegates language handling entirely to the embedding model. When
[`multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small) (or a
larger variant) is used as the embedder, query and document vectors share the same
semantic space across all supported languages. A query in English will retrieve semantically
related documents in Spanish, French, Latin, Arabic, or any of the 100+ languages the model
covers.

The asymmetric prefix convention matters:

| Input type | Required prefix |
|------------|-----------------|
| Document at ingest time | `"passage: "` |
| Query at search time | `"query: "` |

The public alcove codebase applies these prefixes automatically in
`alcove/index/embedder.py` when a multilingual-e5 model is detected.

---

## Configuring a multilingual embedder

```bash
# Install sentence-transformers
pip install sentence-transformers

# Run with the small multilingual model (384-dim, fast)
alcove serve --embedder sentence-transformers --model intfloat/multilingual-e5-small

# Or the larger model for better cross-lingual precision
alcove serve --embedder sentence-transformers --model intfloat/multilingual-e5-large
```

Model sizes at a glance:

| Model | Dimensions | Size | Languages |
|-------|-----------|------|-----------|
| `multilingual-e5-small` | 384 | ~110 MB | 100+ |
| `multilingual-e5-base` | 768 | ~280 MB | 100+ |
| `multilingual-e5-large` | 1024 | ~560 MB | 100+ |

---

## Documented community deployments

Language coverage reported by Alcove deployments:

- **English** — base case; all models perform well
- **Spanish** — Catholic primary sources, legal documents
- **Latin** — patristic texts, ecclesiastical records
- **French** — archival collections, philosophical texts
- **German** — theological and historical archives
- **Samoan**, **Ojibwe**, **Tongan** — endangered language preservation
  (see [Endangered and minority languages](#endangered-and-minority-languages))

---

## Endangered and minority languages

Alcove is a reasonable fit for endangered language preservation. The relevant stack:

- **Audio transcription** via [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper)
  for elder recordings and oral histories
- **OCR** for scanned curriculum materials and handwritten documents
- **Multilingual embeddings** for cross-document search where training data exists

The deployment model matters. An institution running Alcove on its own hardware keeps data
inside the community — no recordings, transcripts, or documents go to an external service.
This is a meaningful difference from cloud-based alternatives for communities where data
sovereignty is a concern.

Grant paths worth noting:

- [IMLS](https://www.imls.gov) — Institute of Museum and Library Services
- [Administration for Native Americans Language Preservation Program](https://www.acf.hhs.gov/ana/grants/language-preservation-and-maintenance)
- [NEH Digital Humanities](https://www.neh.gov/grants/odh) — National Endowment for the Humanities

---

## Constructed languages

[D'ni](https://en.wikipedia.org/wiki/D%27ni_(Myst)), [Klingon](https://en.wikipedia.org/wiki/Klingon_language),
[Na'vi](https://en.wikipedia.org/wiki/Na%27vi_language), and Tolkien's languages
([Quenya](https://en.wikipedia.org/wiki/Quenya), [Sindarin](https://en.wikipedia.org/wiki/Sindarin))
are too sparse for semantic embeddings — the training data does not exist at the scale
these models require.

The practical approach: use metadata-only retrieval. Filter by language tag, canon status
(official vs. fan-created), and source. Full-text search over the corpus handles exact or
near-exact matches. Skip the vector index for these collections.

---

## See also

- [PLUGINS.md — Language & Linguistics](PLUGINS.md#language--linguistics)
- [docs/plugins/language.md](plugins/language.md) — full plugin detail
- [ARCHITECTURE.md](ARCHITECTURE.md) — embedder interface
