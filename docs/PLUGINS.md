# Plugin Ideas & Domain Recipes

Potential Alcove plugins and the use cases that motivate them. Not all are implemented — this is a catalog of what's possible given the plugin architecture.

> **Gate question for every plugin:** "Do we need to build this ourselves, or have some nerds already done this work for us?"

Alcove is domain expert in one thing: its own source code. Everything else is a plugin. Two principles apply: wrap existing domain tooling rather than rebuilding it, and prefer a **view layer over a copy layer** — store manifests with provenance metadata, not duplicated data.

See [ARCHITECTURE.md](ARCHITECTURE.md#plugin-system) for the plugin interface contract.

---

## Domain Verticals

Fifteen verticals identified. The gate question separates them:

**Deep nerd coverage — plugin and go:** birding, bioacoustics, music production, podcasting, film/post-production, photography, academic research, streaming/Twitch.

**Partial coverage — some glue needed:** legal/e-discovery, journalism, real estate, insurance/claims, compliance/audit, architecture/construction.

---

## Audio

| Plugin | Libraries | What it enables |
|--------|-----------|-----------------|
| **Speech transcription** | `faster-whisper` | Any spoken audio → time-coded searchable text. Oral histories, interviews, field notes. |
| **Speaker diarization** | `pyannote.audio` | Who said what. Combine with Whisper: every chunk gets a speaker label. |
| **Semantic audio search** | `laion-clap` | CLAP embeds audio and text in the same space. Query: "rain on a metal roof," "someone laughing." |
| **Sound classification** | YAMNet (`tensorflow`) | 521 sound event categories as metadata tags. Categorize mixed archives automatically. |
| **Music fingerprinting** | `pyacoustid`, `chromaprint` | Identify songs in any audio file via AcoustID. Personal music libraries; copyright scanning. |
| **Bioacoustics** | `birdnetlib`, `opensoundscape` | Species detection from field recordings — birds, bats, frogs, marine mammals. See Birding vertical. |
| **Ocean hydrophones** | `soundfile`, `scipy` | Index passive acoustic archives: whale calls, shipping events, seismic activity. Data stays at the institution. |

---

## Video

| Plugin | Libraries | What it enables |
|--------|-----------|-----------------|
| **Scene detection** | `scenedetect`, `opencv-python` | Cut video into segments at scene boundaries; describe keyframes; index by timestamp. |
| **Object detection** | `ultralytics` (YOLOv8) | Tag segments by detected objects. "All clips with a whiteboard visible." |
| **OCR on frames** | `pytesseract`, `paddleocr` | Text in video — slides, signs, whiteboards — extracted and indexed. |
| **Video understanding** | `ollama` + LLaVA-Video | Natural language questions answered with timestamp grounding. |
| **Twitch / VOD** | `yt-dlp`, `faster-whisper` | Transcribe any platform VOD; make a streamer's back-catalog searchable. |

---

## Photos & Personal Media

| Plugin | Libraries | What it enables |
|--------|-----------|-----------------|
| **CLIP photo search** | `open-clip-torch` | Semantic photo search on your own hardware. No upload, no cloud. |
| **Face clustering** | `facenet-pytorch` | Group by person locally. No biometric data leaves the machine. |
| **EXIF / GPS** | `exifread` | Location, date, camera as structured metadata. Compound queries with semantic embeddings. |
| **Scene classification** | Places365 (`torch`) | 365 location categories as tags — beach, forest, kitchen, gallery. |
| **iCloud Photo Library** | `osxphotos` | Read the local library directly on macOS; extract Apple's own metadata. |

---

## Domain Vertical: Birding & Ornithology

The birding community has already built the stack. Alcove wraps it as local-first infrastructure.

- **BirdNET** (`birdnetlib`): 6,000+ species detection from audio. Timestamp + confidence per detection.
- **eBird API 2.0**: Real-time and historical sighting data, hotspots, regional lists.
- **ebirdst**: Species abundance rasters, range maps, migration routes.
- **Macaulay Library**: 84M+ wildlife media assets, Cornell-hosted, API-accessible.
- **NABirds**: 48K annotated images across 555 North American species.

Cross-reference your field recordings against eBird occurrence data. Query: "detections that don't match expected seasonal presence," "species not yet on my county list."

---

## Text & Documents

A grab-bag of format support that broadens what a corpus can contain:

- **Office formats** (`python-pptx`, `openpyxl`, `odfpy`): Slide decks, spreadsheets, OpenDocument.
- **RTF** (`striprtf`): Legacy word processing. Archives are full of it.
- **HTML / web archives** (`trafilatura`, `beautifulsoup4`): Downloaded sites, WARC files, browser exports.
- **Markdown** (`mistletoe`): Obsidian vaults, Logseq graphs, wiki exports. Chunk by heading.
- **Schema.org Recipe** (`extruct`, `recipe-scrapers`): Structured ingredient/method data for natural-language recipe search.
- **Inventory scanning** (`pyzbar`, vision model): Barcode → product data → searchable inventory record.

---

## Language & Linguistics

- **Multilingual** (`sentence-transformers` multilingual-e5): Cross-lingual search works out of the box. Documented deployments: English, Spanish, Latin, French, German, Samoan, Ojibwe, Tongan, and others.
- **Endangered languages**: Audio transcription + OCR for elder recordings, curriculum materials, oral histories. Deployment model: institution runs Alcove on its own hardware; data does not leave the community. Grant paths: IMLS, ANA Language Preservation, NEH Digital Humanities.
- **Constructed languages** (D'ni, Klingon, Na'vi, Tolkien): Too sparse for semantic embeddings. Use metadata-only retrieval: filter by language, canon status, source.

---

## Embedder & Backend Alternatives

**Domain embedders** — swap the default for better in-domain retrieval:
- Legal: `legal-bert`
- Biomedical / scientific: `allenai/specter2`, `BiomedNLP-BiomedBERT`
- Apple Silicon: `mlx-lm` for on-device throughput

**Vector backends** — alternatives to ChromaDB:
- `sqlite-vec`: Single-file, zero external process. Copy the `.db`, move the index.
- `qdrant-client`: Lighter at scale; built-in sparse vector support for hybrid retrieval.
- `weaviate-client`: Native BM25 + vector hybrid; strong metadata filter API.

---

## Building a Plugin

```toml
[project.entry-points."alcove.extractors"]
wav  = "my_audio_plugin:extract_audio"
flac = "my_audio_plugin:extract_audio"
```

Plugins are discovered at startup, override builtins for shared extension names, and appear in `alcove plugins`. Authentication is out of scope — access control belongs at the deployment boundary.
