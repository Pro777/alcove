# Seed Corpus

Alcove includes a small runtime-fetched seed corpus for deterministic demos. All texts are public domain.

Why include a seed corpus? Because you should be able to search something real before you commit your own files. See [Why Alcove exists](../WHY.md) for context on why this matters.

## Why these sources

Legally clear: public-domain texts only. Tangible: recognizable, human-readable content for immediate search demos. Small footprint: no large binaries committed to the repository. Reproducible: each file validated against a SHA-256 manifest.

## Included sources

1. **Alice's Adventures in Wonderland** (Project Gutenberg #11)
   - URL: `https://www.gutenberg.org/files/11/11-0.txt`
   - Public domain in the U.S.

2. **Frankenstein; Or, The Modern Prometheus** (Project Gutenberg #84)
   - URL: `https://www.gutenberg.org/files/84/84-0.txt`
   - Public domain in the U.S.

3. **The Federalist Papers** (Project Gutenberg #1404)
   - URL: `https://www.gutenberg.org/files/1404/1404-0.txt`
   - Public domain in the U.S.

4. **Declaration of Independence** (U.S. National Archives)
   - URL: `https://www.archives.gov/founding-docs/declaration-transcript`
   - U.S. federal government work; public domain.

5. **U.S. Constitution** (U.S. National Archives)
   - URL: `https://www.archives.gov/founding-docs/constitution-transcript`
   - U.S. federal government work; public domain.

## Reproducibility

```bash
python3 scripts/fetch_seed_corpus.py
```

Downloads files into `data/raw/seed/` and verifies each against the SHA-256 checksums in `scripts/seed_manifest.json`. If a checksum fails, the script exits with a non-zero status.

To run the seed corpus demo and see Alcove in action: [Setup takes three commands](OPERATIONS.md#first-run).
