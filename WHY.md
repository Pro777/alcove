# Why Alcove exists

## Index your world.

You have thousands of files. You can never find anything in them.

Alcove fixes that. Point it at a folder. It reads everything: PDFs, Word docs, ebooks, spreadsheets, HTML, Markdown, plain text ([full format list](docs/ARCHITECTURE.md#supported-formats)). It builds a searchable index and lets you search by meaning, not just by filename.

Everything stays on your machine. No upload. No account. No tracking. This is not a privacy feature. It is [the architecture](docs/ARCHITECTURE.md). The [security model](docs/SECURITY.md#security-model) is simple: there is no outbound path for your data because none was ever built.

Want to see it work before reading further? The [seed corpus](docs/SEED_CORPUS.md) ships with public-domain texts (Alice in Wonderland, the Federalist Papers, the U.S. Constitution) so you can search something real in under a minute. [Setup takes three commands.](docs/OPERATIONS.md#first-run)

## Share it with the universe.

AI tools can only work with what they can see. Right now, that means: upload your files, hand them over, hope for the best.

Alcove flips that. Instead of sending your documents to the AI, the AI asks Alcove. Your files stay put. The AI gets answers from your actual documents. No copies leave. No guessing. No making things up.

You pick which collections are visible. You pick which tools can ask. Your door, your keys.

## What is coming.

**Soon:** Auto-indexing when files change ([streaming ingest](docs/ROADMAP.md#near-term)). A [browse mode](docs/ROADMAP.md#near-term) to explore your collection, not just search it. More formats: PowerPoint, Excel, RTF. And the [MCP endpoint](docs/ROADMAP.md#near-term): an AI retrieval interface so Claude, ChatGPT, and other tools can query your index directly.

**Next:** Indexing beyond text: audio, images, video ([cross-modal indexing](docs/ROADMAP.md#mid-term)). A [relevance layer](docs/ROADMAP.md#mid-term) that works like memory: things you use often surface faster, things you have not touched fade.

**Later:** [Federated search](docs/ROADMAP.md#long-term) across multiple Alcove installations. Your team and another team query each other's indexes without sharing raw files. Sovereign data, shared knowledge. Plus a [desktop app](docs/ROADMAP.md#long-term) so none of this requires a terminal.

These are the direction, not promises. Full plan: [ROADMAP.md](docs/ROADMAP.md).

## The tension is the product.

Most software picks a side: locked down, or accessible. Alcove holds both. Your files never leave. Your knowledge travels, on your terms.

The universe is building an AI layer on top of everything. Someone should make sure you get to decide whether your world is included.
