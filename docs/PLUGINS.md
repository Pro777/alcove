# Plugin Ideas & Domain Recipes

Potential Alcove plugins and the use cases that motivate them. Not all are implemented — this is a catalog of what's possible given the plugin architecture.

> **Gate question for every plugin:** "Has the community already solved this, or do we need to build it ourselves?"

Alcove is domain expert in one thing: its own source code. Everything else is a plugin. Two principles apply: wrap existing domain tooling rather than rebuilding it, and prefer a **view layer over a copy layer** — store manifests with provenance metadata, not duplicated data.

Two system boundaries that apply to every plugin:

- **Retrieval only.** Plugins index and return documents. They do not perform generative transformations on content.
- **Offline by default.** Alcove makes no outbound network calls unless a plugin explicitly requires one (e.g., an API fetch at ingest time). Plugins must not send corpus data to external services.

See [ARCHITECTURE.md](ARCHITECTURE.md#plugin-system) for the plugin interface contract.

---

## Verticals

The gate question separates verticals into two tiers:

**Strong community tooling — plugin and go:** birding, bioacoustics, music production, podcasting, film/post-production, photography, academic research, streaming/Twitch.

**Partial coverage — some glue needed:** legal/e-discovery, journalism, real estate, insurance/claims, compliance/audit, architecture/construction.

---

## Audio

Speech, sound classification, music fingerprinting, bioacoustics, and hydrophone archives. [Full detail →](plugins/audio.md)

| Plugin | Library | Description |
|--------|---------|-------------|
| [Speech transcription](plugins/audio.md#speech-transcription) | [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) | Converts spoken audio to time-coded searchable text. |
| [Speaker diarization](plugins/audio.md#speaker-diarization) | [`pyannote.audio`](https://github.com/pyannote/pyannote-audio) | Segments audio by speaker; pairs with transcription for labeled chunks. |
| [Semantic audio search](plugins/audio.md#semantic-audio-search) | [`laion-clap`](https://github.com/LAION-AI/CLAP) | Text-to-audio search with no transcription required. |
| [Sound classification](plugins/audio.md#sound-classification) | [YAMNet](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet) | Tags audio with 521 sound event categories from AudioSet. |
| [Music fingerprinting](plugins/audio.md#music-fingerprinting) | [`pyacoustid`](https://github.com/beetbox/pyacoustid), [`chromaprint`](https://acoustid.org/chromaprint) | Identifies recordings via AcoustID and MusicBrainz. |
| [Bioacoustics](plugins/audio.md#bioacoustics) | [`birdnetlib`](https://github.com/joeweiss/birdnetlib), [`opensoundscape`](https://github.com/kitzeslab/opensoundscape) | Species detection from field recordings. |
| [Ocean hydrophones](plugins/audio.md#ocean-hydrophone-archives) | [`soundfile`](https://github.com/bastibe/python-soundfile), [`scipy`](https://scipy.org) | Indexes passive acoustic monitoring archives locally. |

---

## Video

Scene detection, object tagging, OCR on frames, local video understanding, and VOD transcription. [Full detail →](plugins/video.md)

| Plugin | Library | Description |
|--------|---------|-------------|
| [Scene detection](plugins/video.md#scene-detection) | [`scenedetect`](https://github.com/Breakthrough/PySceneDetect), [`opencv-python`](https://github.com/opencv/opencv-python) | Cuts video at scene boundaries and indexes keyframes by timestamp. |
| [Object detection](plugins/video.md#object-detection) | [`ultralytics`](https://github.com/ultralytics/ultralytics) (YOLOv8) | Tags video segments with detected object categories. |
| [OCR on frames](plugins/video.md#ocr-on-frames) | [`pytesseract`](https://github.com/madmaze/pytesseract), [`paddleocr`](https://github.com/PaddlePaddle/PaddleOCR) | Extracts text from slides, signs, and whiteboards visible in video. |
| [Video understanding](plugins/video.md#video-understanding) | [`ollama`](https://ollama.com) + LLaVA-Video | Answers natural-language questions about video content with timestamp grounding. |
| [VOD transcription](plugins/video.md#vod-transcription-twitch--youtube--etc) | [`yt-dlp`](https://github.com/yt-dlp/yt-dlp), [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) | Transcribes any platform VOD and makes it searchable. |

---

## Photos & Personal Media

Semantic photo search, face clustering, EXIF metadata, scene tagging, and iCloud library access. [Full detail →](plugins/photos.md)

| Plugin | Library | Description |
|--------|---------|-------------|
| [CLIP photo search](plugins/photos.md#clip-photo-search) | [`open-clip-torch`](https://github.com/mlfoundations/open_clip) | Semantic photo search on local hardware, no upload required. |
| [Face clustering](plugins/photos.md#face-clustering) | [`facenet-pytorch`](https://github.com/timesler/facenet-pytorch) | Groups photos by person locally; no biometric data leaves the machine. |
| [EXIF / GPS](plugins/photos.md#exif-and-gps-metadata) | [`exifread`](https://github.com/ianare/exif-py) | Extracts location, date, and camera metadata as structured fields. |
| [Scene classification](plugins/photos.md#scene-classification) | [Places365](http://places2.csail.mit.edu) / [`torch`](https://pytorch.org) | Tags photos with 365 location categories. |
| [iCloud Photo Library](plugins/photos.md#icloud-photo-library-macos) | [`osxphotos`](https://github.com/RhetTbull/osxphotos) | Reads the local macOS Photos library and its metadata directly. |

---

## Birding & Ornithology

The birding community has a deep, well-maintained stack. Alcove wraps it as local-first infrastructure. [Full detail →](plugins/birding.md)

| Plugin | Library / API | Description |
|--------|--------------|-------------|
| [BirdNET detection](plugins/birding.md#birdnet-audio-detection) | [`birdnetlib`](https://github.com/joeweiss/birdnetlib) | Detects 6,000+ species from audio with timestamps and confidence scores. |
| [eBird API](plugins/birding.md#ebird-api-20) | [eBird API 2.0](https://documenter.getpostman.com/view/664302/S1ENwy59) | Real-time and historical sighting data, hotspots, regional lists. |
| [Range data](plugins/birding.md#species-range-and-abundance-data) | [`ebirdst`](https://github.com/CornellLabofOrnithology/ebirdst) | Species abundance rasters and migration routes. |
| [Macaulay Library](plugins/birding.md#macaulay-library-integration) | [Cornell API](https://www.macaulaylibrary.org) | Cross-reference detections against 84M+ wildlife media assets. |
| [NABirds](plugins/birding.md#nabirds-image-reference) | [NABirds v1](https://dl.allaboutbirds.org/nabirds) | 48K annotated images for image-based species identification. |

---

## Text & Documents

Format support for Office files, RTF, HTML archives, Markdown, recipe data, and inventory scanning. [Full detail →](plugins/text-and-documents.md)

| Plugin | Library | Description |
|--------|---------|-------------|
| [Office formats](plugins/text-and-documents.md#office-formats) | [`python-pptx`](https://github.com/scanny/python-pptx), [`openpyxl`](https://openpyxl.readthedocs.io), [`odfpy`](https://github.com/eea/odfpy) | Extracts text from slide decks, spreadsheets, and OpenDocument files. |
| [RTF](plugins/text-and-documents.md#rtf) | [`striprtf`](https://github.com/joshy/striprtf) | Handles legacy RTF files common in legal and archival collections. |
| [HTML / web archives](plugins/text-and-documents.md#html-and-web-archives) | [`trafilatura`](https://github.com/adbar/trafilatura), [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) | Extracts main content from downloaded pages and WARC files. |
| [Markdown](plugins/text-and-documents.md#markdown) | [`mistletoe`](https://github.com/miyuchina/mistletoe) | Chunks Obsidian vaults, Logseq graphs, and wiki exports by heading. |
| [Recipe data](plugins/text-and-documents.md#recipe-data) | [`extruct`](https://github.com/scrapinghub/extruct), [`recipe-scrapers`](https://github.com/hhursev/recipe-scrapers) | Extracts structured ingredient and method data from Schema.org markup. |
| [Inventory scanning](plugins/text-and-documents.md#inventory-scanning) | [`pyzbar`](https://github.com/NaturalHistoryMuseum/pyzbar) + vision model | Reads barcodes and creates searchable inventory records. |

---

## Language & Linguistics

Multilingual search, endangered language support, and constructed language guidance. [Full detail →](plugins/language.md)

| Topic | Description |
|-------|-------------|
| [Multilingual](plugins/language.md#multilingual-search) | Cross-lingual search via [multilingual-e5](https://huggingface.co/intfloat/multilingual-e5-large); 100+ languages, no per-language config. |
| [Endangered languages](plugins/language.md#endangered-and-minority-languages) | Audio transcription and OCR for oral histories and curriculum materials; data stays local. |
| [Constructed languages](plugins/language.md#constructed-languages) | Too sparse for embeddings; use metadata-only retrieval. |

---

## Academic & Scholarly Publishing

BibTeX sidecars, ORCID extraction, DOI normalization, and license classification. [Full detail →](plugins/academic.md)

| Plugin | Library | Description |
|--------|---------|-------------|
| [BibTeX sidecar](plugins/academic.md#bibtex-sidecar) | [`bibtexparser`](https://github.com/sciunto-org/python-bibtexparser) | Parses `.bib` files alongside PDFs; author, DOI, abstract become searchable metadata. |
| [ORCID extraction](plugins/academic.md#orcid-id-extraction) | [ORCID](https://orcid.org) + stdlib | Validates and extracts ORCID iDs from author fields. |
| [DOI normalization](plugins/academic.md#doi-normalization) | [DOI](https://www.doi.org) + stdlib | Canonicalizes DOIs from any format for reliable deduplication. |
| [CC license classification](plugins/academic.md#creative-commons-license-classification) | [Creative Commons](https://creativecommons.org/licenses/) + stdlib | Maps license strings to canonical CC identifiers. |

---

## Embedders & Backend Alternatives

Swap the default embedder or vector store for domain-specific or scale requirements. [Full detail →](plugins/embedders-and-backends.md)

| Option | Description |
|--------|-------------|
| [Domain embedders](plugins/embedders-and-backends.md#domain-embedders) | [legal-bert](https://huggingface.co/nlpaueb/legal-bert-base-uncased), [specter2](https://huggingface.co/allenai/specter2), [BiomedBERT](https://huggingface.co/microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext), [mlx-lm](https://github.com/ml-explore/mlx-lm) for Apple Silicon. |
| [SQLite-vec](plugins/embedders-and-backends.md#vector-backends) | [sqlite-vec](https://github.com/asg017/sqlite-vec) — single-file index, zero external process. |
| [Qdrant](plugins/embedders-and-backends.md#vector-backends) | [qdrant-client](https://github.com/qdrant/qdrant-client) — lighter at scale; built-in sparse vector support. |
| [Weaviate](plugins/embedders-and-backends.md#vector-backends) | [weaviate-client](https://github.com/weaviate/weaviate-python-client) — native BM25+vector hybrid; strong metadata filter API. |

---

## Building a Plugin

```toml
[project.entry-points."alcove.extractors"]
wav  = "my_audio_plugin:extract_audio"
flac = "my_audio_plugin:extract_audio"
```

Plugins are discovered at startup, override built-ins for shared extension names, and appear in `alcove plugins`. Authentication is not built into Alcove. Place it behind a reverse proxy that enforces authn/authz at the deployment boundary — OAuth, mTLS, or an API gateway all work.
