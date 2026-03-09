<img src="docs/assets/logo.svg" alt="Alcove" height="56">

<p>
  <a href="https://github.com/Pro777/alcove/actions/workflows/ci.yml"><img src="https://github.com/Pro777/alcove/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/alcove-search/"><img src="https://img.shields.io/pypi/v/alcove-search.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/alcove-search/"><img src="https://img.shields.io/pypi/pyversions/alcove-search.svg" alt="Python Versions"></a>
  <a href="https://github.com/Pro777/alcove/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
</p>

**Index your world. Share it with the universe.**

Alcove is collective memory infrastructure for people who keep their data on their own disk. You point it at a directory of documents. It chunks, embeds, and indexes them locally. You search. Nothing leaves your machine.

That is the whole idea. Your files are already on your computer; moving them somewhere else to make them searchable was always the odd decision. Alcove skips that step.

> **[Watch the 30-second demo](https://pro777.github.io/alcove/demo.html)**

## How it works

Alcove runs a three-stage pipeline: ingest, index, query. Each stage is independent and pluggable.

```
data/raw/*  →  chunks.jsonl  →  vector store  →  search results
```

**Ingest** discovers files recursively and extracts text using format-specific extractors. PDF, EPUB, HTML, Markdown, CSV, JSON, JSONL, DOCX, RST, TSV, and plain text all work out of the box. 

**Index** embeds the chunks and writes them to a local vector store (ChromaDB by default; zvec as an alternative). 

**Query** retrieves results through a CLI or a built-in web interface with upload support.

The pipeline is fixed. The corpus is variable. That makes Alcove a platform, not a product: the same architecture indexes a personal research library, a community archive, or a municipal records collection.

## Quick start

**Requirements:** Python 3.10+

```bash
pip install alcove-search
alcove seed-demo          # download a public-domain corpus and build the index
alcove serve              # open http://localhost:8000
```

<img src="docs/assets/web-ui-screenshot.png" alt="Alcove web UI" width="760">

For real semantic search, install the optional extras:

```bash
pip install alcove-search[semantic]    # sentence-transformers (~80 MB model, first run only)
pip install alcove-search[epub,docx]   # additional format support
```

## Trust model

Alcove stores documents and vectors on local disk only. It makes no outbound network calls. It collects no telemetry. ChromaDB's upstream telemetry is disabled by default. The web server binds to localhost.

We do not want your data.

This is not a feature; it is a design constraint. Local-first is not something Alcove does. It is what Alcove is. The architecture assumes the operator owns the hardware, controls the storage, and decides what enters the index. There is no hosted control plane. There is no account to create.

If you need encryption at rest, use your operating system's disk encryption. If you need authentication, put a reverse proxy in front of the API. Alcove handles search. You handle custody.

## Extending Alcove

Three plugin surfaces are available via Python entry points: extractors (new file formats), embedders (new models), and backends (new vector stores). Plugins are discovered at runtime and take precedence over builtins.

```bash
alcove plugins            # list installed plugins
alcove status             # show index + configuration
```

See [Architecture](docs/ARCHITECTURE.md) for the full plugin API.

## Where it is going

The current release (v0.3.0) is a working search platform. The trajectory is broader: streaming ingest, browsable corpus navigation, an agent-facing query surface, and eventually cross-modal indexing beyond text. The full roadmap is in [docs/ROADMAP.md](docs/ROADMAP.md).

Alcove will not become a SaaS product.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Operations](docs/OPERATIONS.md)
- [Security](docs/SECURITY.md)
- [Seed Corpus](docs/SEED_CORPUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Accessibility](ACCESSIBILITY.md)

## License

[Apache 2.0](LICENSE)
