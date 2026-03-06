# 📚 Seed Corpus (Public Domain Only)

Alcove includes a tiny runtime-fetched seed corpus for deterministic demos.

## 🤔 Why these sources

- **Legally clear** — public-domain texts only
- **Tangible** — recognizable, human-readable content for immediate search demos
- **Small footprint** — no large binaries committed
- **Reproducible** — source URL + SHA-256 manifest validation

## 📖 Included sources

1. **Alice's Adventures in Wonderland** (Project Gutenberg #11)
   - URL: `https://www.gutenberg.org/files/11/11-0.txt`
   - Public domain status: Project Gutenberg public-domain text in the U.S.

2. **Frankenstein; Or, The Modern Prometheus** (Project Gutenberg #84)
   - URL: `https://www.gutenberg.org/files/84/84-0.txt`
   - Public domain status: Project Gutenberg public-domain text in the U.S.

3. **The Federalist Papers** (Project Gutenberg #1404)
   - URL: `https://www.gutenberg.org/files/1404/1404-0.txt`
   - Public domain status: historical U.S. government-era text; public domain in U.S.

4. **Declaration of Independence (Transcript)** (U.S. National Archives)
   - URL: `https://www.archives.gov/founding-docs/declaration-transcript`
   - Public domain status: U.S. federal government work (public domain)

5. **U.S. Constitution (Transcript)** (U.S. National Archives)
   - URL: `https://www.archives.gov/founding-docs/constitution-transcript`
   - Public domain status: U.S. federal government work (public domain)

## 🔁 Reproducibility

```bash
python3 scripts/fetch_seed_corpus.py
```

Downloads files into `data/raw/seed/` and verifies each SHA-256 from `scripts/seed_manifest.json`.
