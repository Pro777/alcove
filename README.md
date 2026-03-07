<img src="docs/assets/logo.svg" alt="Alcove" height="56">

<p>
  <a href="https://github.com/Pro777/alcove/actions/workflows/ci.yml"><img src="https://github.com/Pro777/alcove/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/alcove-search/"><img src="https://img.shields.io/pypi/v/alcove-search.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/alcove-search/"><img src="https://img.shields.io/pypi/pyversions/alcove-search.svg" alt="Python Versions"></a>
  <a href="https://github.com/Pro777/alcove/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
</p>

**Index your world. Share it with the universe.**

**Alcove** is a local-first document search library. Install it, point it at your files, and search. No server, no sign-up, no data leaves your disk.

> **[Watch the 30-second demo](https://pro777.github.io/alcove/demo.html)**

## ✨ Features

- **🔒 Private** — documents stay on your machine, no cloud calls, no telemetry
- **⚡ Zero config** — `pip install`, two commands, searching in under a minute
- **🔌 Extensible** — custom extractors, embedders, and vector backends
- **📄 Multi-format** — PDF, EPUB, HTML, Markdown, CSV, JSON, JSONL, DOCX, TXT
- **🌐 Web UI** — upload and search from your browser

## 📦 Installation

**Requirements:** Python 3.10+ · Linux, macOS, or Windows

```bash
pip install alcove-search
```

**Optional extras:**

| Extra | Install command | What it adds |
|-------|----------------|--------------|
| Semantic search | `pip install alcove-search[semantic]` | Real vector similarity via sentence-transformers (~80 MB model download on first use) |
| EPUB support | `pip install alcove-search[epub]` | `.epub` file ingestion |
| DOCX support | `pip install alcove-search[docx]` | `.docx` file ingestion |

## ⚡ Quick Start

```bash
alcove seed-demo          # download sample corpus + build index
alcove serve              # open http://localhost:8000
```

<img src="docs/assets/web-ui-screenshot.png" alt="Alcove web UI" width="760">

## 🔒 Trust Model

- Local disk only — no hosted control plane
- No telemetry. Period. (ChromaDB's upstream telemetry is also disabled.)
- You choose what enters your index
- **We do not want your data**

## 📚 Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Operations](docs/OPERATIONS.md)
- [Security](docs/SECURITY.md)
- [Seed Corpus](docs/SEED_CORPUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Accessibility](ACCESSIBILITY.md)

## 📄 License

[Apache 2.0](LICENSE)
