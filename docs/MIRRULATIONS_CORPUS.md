# Mirrulations Corpus Evaluation

Issue `#151` asks whether Mirrulations is a good real-world Alcove test corpus. The short answer is yes, with one constraint: use a scoped, text-only subset first.

## Why it fits Alcove

- It is a real federal document corpus with the exact failure modes Alcove needs to handle: HTML notices, extracted PDF text, public comments, and noisy attachment text.
- The hierarchy is already split into text and binary trees, so Alcove can stay on the text side for the first pass and avoid downloading large attachment binaries.
- The corpus is large enough to stress retrieval quality, chunking, and operator workflows without requiring any Alcove-specific schema upstream.

## Recommendation

Start with a pilot subset on `rowan-den`:

- agencies: `EPA`, `HHS`, `DOL`, `SEC`, `FCC`
- data shape: only `text-<docket>` trees
- first-pass inputs:
  - `docket/*.json`
  - `documents/*.json`
  - `documents/*_content.htm`
  - `documents_extracted_text/*/*.txt`
  - `comments/*.json`
  - `comments_extracted_text/*/*.txt`
- keep binaries out of the first ingest pass

This gives Alcove a messy regulatory corpus immediately, while keeping storage and sync time bounded enough for iteration.

## What the repo now supports

`alcove mirrulations-demo` ingests a local Mirrulations text subset into a dedicated collection, `mirrulations_docs`.

It normalizes:

- docket JSON into one retrieval record per docket
- document JSON plus `_content.htm` into one retrieval record per document
- comment JSON into one retrieval record per public comment
- extracted attachment text into one retrieval record per attachment text file

## Usage

Sync a scoped text-only subset from the public S3 mirror. This example keeps only the text artifacts Alcove can use immediately:

```bash
aws s3 sync --no-sign-request \
  s3://mirrulations/EPA/ \
  data/raw/mirrulations/EPA/ \
  --exclude "*" \
  --include "*/text-*/docket/*.json" \
  --include "*/text-*/documents/*.json" \
  --include "*/text-*/documents/*_content.htm" \
  --include "*/text-*/documents_extracted_text/*/*.txt" \
  --include "*/text-*/comments/*.json" \
  --include "*/text-*/comments_extracted_text/*/*.txt"
```

Index the synced subset into its own collection:

```bash
alcove mirrulations-demo data/raw/mirrulations --agency EPA --agency HHS --jsonl-out data/processed/mirrulations.jsonl
```

Query that collection:

```bash
alcove search "power plant emissions limits" --collection mirrulations_docs
```

## Notes

- Mirrulations field coverage varies by docket, so the loader is intentionally defensive and only indexes text fields that are present.
- The first pass is meant to validate retrieval quality and ingestion robustness, not to mirror the full `27M`-document corpus locally.
- If the pilot works, the next logical step is a repeatable sync script for named dockets or date windows.
