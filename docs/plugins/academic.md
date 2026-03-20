# Academic & Scholarly Publishing Plugins

These plugins add structured academic metadata to ingested documents. They are most useful when ingesting journal articles, preprints, or institutional repositories where citation context matters.

## BibTeX Sidecar

**Library:** [`bibtexparser`](https://github.com/sciunto-org/python-bibtexparser) ([BibTeX](https://en.wikipedia.org/wiki/BibTeX) format)

Parses `.bib` files alongside PDFs. Author, title, year, journal, DOI, and abstract become searchable metadata attached to every chunk from the corresponding document. The sidecar approach lets you maintain your existing bibliography workflow and have Alcove pick up the structured data automatically.

Place the `.bib` file alongside the PDF with the same base name. The plugin detects the pair on ingest.

## ORCID iD Extraction

**Standard:** [ORCID](https://orcid.org) iD format (stdlib + regex)

Validates and extracts [ORCID iDs](https://orcid.org) from BibTeX author fields. An ORCID iD in metadata lets you query a corpus by researcher identifier rather than name string, which handles name ambiguity and name changes correctly.

Format handled: bare iD (0000-0002-1825-0097) and URL form (https://orcid.org/0000-0002-1825-0097).

## DOI Normalization

**Standard:** [DOI](https://www.doi.org) (stdlib + regex)

Validates and canonicalizes DOIs from any format. Handles bare DOIs, doi.org URLs, and dx.doi.org URLs. The output is always a canonical bare DOI. This enables reliable deduplication when the same paper arrives from multiple sources with different DOI formatting.

## Creative Commons License Classification

**Standard:** [Creative Commons](https://creativecommons.org/licenses/) license strings (stdlib)

Classifies license strings into canonical [Creative Commons](https://creativecommons.org/licenses/) identifiers: CC0, CC-BY, CC-BY-SA, CC-BY-NC, CC-BY-ND, CC-BY-NC-SA, CC-BY-NC-ND. Also determines display permissions: whether the work can be reproduced, whether attribution is required, whether commercial use is allowed.

Useful for institutional repositories where license status affects what the system can surface externally.

---

## Combined Workflow

These four plugins compose. Ingest a PDF alongside its `.bib` sidecar: every chunk carries author, DOI, license, and ORCID metadata, all queryable alongside the text content.

Example queries that become possible:
- "Papers by this ORCID author on this topic"
- "CC-BY articles from 2020-2023 about X"
- "All papers in this repository that lack a DOI" (deduplication audit)
