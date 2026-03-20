# Birding & Ornithology Plugins

The birding community has a mature, well-maintained tooling stack. Alcove wraps it as local-first infrastructure. The gate question applies here: there is no need to build species detection or occurrence databases from scratch. The libraries and APIs already exist.

## BirdNET Audio Detection

**Library:** [`birdnetlib`](https://github.com/joeweiss/birdnetlib) (wraps [BirdNET-Analyzer](https://github.com/kahst/BirdNET-Analyzer) from [Cornell Lab of Ornithology](https://www.birds.cornell.edu))

Detects bird species from audio recordings. Covers 6,000+ species. Returns detections with timestamp ranges and confidence scores. Run it over a morning field recording and get a list of species detected, when each was heard, and how confident the model is.

BirdNET runs locally. Field recordings stay on your hardware.

## eBird API 2.0

**API:** [Cornell Lab of Ornithology eBird API](https://documenter.getpostman.com/view/664302/S1ENwy59)

Provides real-time and historical sighting data, regional species lists, and hotspot information. Cross-reference your BirdNET detections against eBird occurrence data for the same location and date. Queries like "detections that don't match expected seasonal presence" or "species not yet on my county list" become possible when BirdNET output is indexed alongside eBird data.

Requires a free eBird API key from [ebird.org](https://ebird.org/api/keygen).

## Species Range and Abundance Data

**Library:** [`ebirdst`](https://github.com/CornellLabofOrnithology/ebirdst)

Range maps and seasonal abundance rasters from [eBird Status and Trends](https://science.ebird.org/en/status-and-trends). Each raster represents estimated species abundance across a geographic grid at weekly resolution. Useful for understanding whether a detection at a given location and time of year is expected or anomalous.

## Macaulay Library Integration

**API:** [Cornell Lab of Ornithology — Macaulay Library](https://www.macaulaylibrary.org)

The Macaulay Library holds 84 million+ wildlife media assets, all Cornell-hosted and API-accessible. Cross-reference local recordings against reference audio and video from the library. Useful for verification workflows: compare a detection to known reference recordings for the same species.

## NABirds Image Reference

**Dataset:** [NABirds v1](https://dl.allaboutbirds.org/nabirds)

48,000 annotated images across 555 North American species. Useful as a training or reference dataset when building image-based species identification on top of Alcove. The dataset is available under a research license from Cornell.

---

## Putting It Together

A typical birding workflow on Alcove:

1. Ingest field recordings. BirdNET runs automatically, tagging each audio segment with species detections.
2. Pull eBird occurrence data for the recording location and date range.
3. Flag detections where BirdNET confidence is above threshold but eBird shows the species as rare or absent for that region and season.
4. Query: "What did I record in March that I haven't recorded there before?"

The recordings stay local. The eBird and Macaulay data come in via API at query time or cached on ingest.
