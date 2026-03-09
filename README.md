<img src="docs/assets/logo.svg" alt="Alcove" height="56">

<p>
  <a href="https://github.com/Pro777/alcove/actions/workflows/ci.yml"><img src="https://github.com/Pro777/alcove/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://codecov.io/gh/Pro777/alcove"><img src="https://codecov.io/gh/Pro777/alcove/graph/badge.svg?token=A8R18L65TL" alt="Coverage"></a>
  <a href="https://pypi.org/project/alcove-search/"><img src="https://img.shields.io/pypi/v/alcove-search.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/alcove-search/"><img src="https://img.shields.io/pypi/pyversions/alcove-search.svg" alt="Python Versions"></a>
  <a href="https://github.com/Pro777/alcove/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
</p>

**Index your world. Share it with the universe.**

AI is at the door. Alcove is the deadbolt.

---

Local-first search infrastructure with opinions about who touches your data. No AI unless you say so. Nothing leaves your machine.

**[See it in 30 seconds](https://pro777.github.io/alcove/demo.html)**

## Quick start

```bash
pip install alcove-search[semantic]
```

This is the recommended install for actual document search. It pulls in sentence-transformers for real vector similarity (~80 MB model download on first use). The base package without `[semantic]` uses the hash embedder, which is useful for development and CI but does not produce meaningful search results.

<details>
<summary>All install extras</summary>

| Extra | Install command | What it adds |
|-------|----------------|--------------|
| Semantic search | `pip install alcove-search[semantic]` | Real vector similarity via sentence-transformers |
| EPUB support | `pip install alcove-search[epub]` | `.epub` file ingestion |
| DOCX support | `pip install alcove-search[docx]` | `.docx` file ingestion |
| Everything | `pip install alcove-search[semantic,epub,docx]` | All of the above |

</details>

```bash
alcove seed-demo          # download sample corpus + build index
alcove serve              # open http://localhost:8000
```

<p>
  <a href="docs/assets/web-ui-dark.png">
    <img src="docs/assets/web-ui-dark.png" alt="Alcove UI — dark theme" width="420">
  </a>
  &nbsp;
  <a href="docs/assets/web-ui-light.png">
    <img src="docs/assets/web-ui-light.png" alt="Alcove UI — light theme" width="420">
  </a>
</p>

## How it works

Three stages. Each is independent, each reads from disk and writes to disk, each can be re-run without touching the others.

```
data/raw/*  →  chunks.jsonl  →  vector store  →  search results
```

**Ingest** discovers files recursively and extracts text with format-specific extractors. PDF, EPUB, HTML, Markdown, CSV, JSON, JSONL, DOCX, RST, TSV, and plain text all work out of the box.

**Index** embeds the chunks and writes them to a local vector store. ChromaDB is the default backend; zvec is available where a lighter footprint matters.

**Query** retrieves results through the CLI or a built-in web interface with file upload. Three search modes: semantic (vector similarity), keyword (BM25), and hybrid (both). Results can be scoped to named collections.

Custom extractors, embedders, and vector backends plug in via Python entry points. See [Architecture](docs/ARCHITECTURE.md) for the full plugin API.

## The trust dial

Most search tools give you one mode and call it a feature. Alcove gives you a choice and calls it what it is: a trust decision.

**Hash embedder (default)** -- Deterministic SHA-256. No ML. No model downloads. No network activity. Results are fully reproducible and fully inspectable. Every output is a pure function of the input. This is for people who do not want machine learning touching their corpus at all.

**Sentence-transformers (opt-in)** -- Real vector similarity via a local neural model (~80 MB, downloaded once). Still fully local. Still no cloud. Still no data exfiltration. This is retrieval, not generation -- it finds documents that are semantically close to your query. It does not write anything, invent anything, or editorialize.

You are not choosing between "basic" and "premium." You are choosing your comfort level with ML. Both modes run the same pipeline, produce the same output format, and respect the same boundary: nothing leaves the machine.

## Trust model

Local disk only. No outbound network calls. No telemetry. No account to create. We disabled ChromaDB's upstream telemetry too.

🔒 **We do not want your data.**

This is not a feature we are marketing. It is a structural constraint. The architecture assumes you own your hardware, you control your storage, and you decide what enters the index. There is no flag to turn this off because there is nothing to turn off. The boundary is the architecture.

If you need encryption at rest, use your OS disk encryption. If you need authentication, put a reverse proxy in front of the API. Alcove handles search. You handle custody.

## Where it is going

v0.3.0 is a working search platform. That is the "index your world" part.

The "share it with the universe" part comes next: an MCP retrieval surface that lets Claude, ChatGPT, a public website, or any other tool query your index -- on your terms. Your corpus stays local. Your index stays yours. But if you choose to expose it, the universe can ask it questions and get real answers back. No hallucinations, because there is no generation. Just retrieval.

Beyond that: streaming ingest, browsable corpus navigation, cross-modal indexing, and eventually federated indexes that let separate Alcove instances share a query surface without sharing raw data.

The full roadmap is in [docs/ROADMAP.md](docs/ROADMAP.md). Alcove will not become a SaaS product.

## Documentation

[Architecture](docs/ARCHITECTURE.md) -- [Operations](docs/OPERATIONS.md) -- [Security](docs/SECURITY.md) -- [Seed Corpus](docs/SEED_CORPUS.md) -- [Roadmap](docs/ROADMAP.md) -- [Accessibility](ACCESSIBILITY.md)

## License

[Apache 2.0](LICENSE)
