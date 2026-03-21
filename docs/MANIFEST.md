# Manifest Format & Registry Discovery

Alcove uses an optional `alcove.json` file to declare which plugin and index registries the runtime should consult, and which plugins and indexes are configured for this instance.

This document defines the manifest schema, the registry JSON format, and the design rationale.

---

## Overview

Two primitives:

- **Plugin registry** — a JSON list of installable Alcove plugins (extractors, backends, embedders). Served at a URL; default is `https://plugins.alcove.software/registry.json`.
- **Index registry** — a JSON list of published Alcove search indexes (corpora accessible over a network). Served at a URL; default is `https://search.alcove.software/registry.json`.

Pointing your runtime at a community fork is a single URL change in `alcove.json`.

---

## alcove.json schema

Place `alcove.json` at the root of your Alcove deployment directory (next to `pyproject.toml` or `docker-compose.yml`).

```json
{
  "$schema": "https://alcove.software/schemas/manifest/v1.json",
  "alcove_manifest_version": "1",

  "registries": {
    "plugins": "https://plugins.alcove.software/registry.json",
    "indexes": "https://search.alcove.software/registry.json"
  },

  "plugins": [
    {
      "name": "alcove-audio",
      "version": ">=0.2.0",
      "source": "registry"
    }
  ],

  "indexes": [
    {
      "id": "local",
      "url": "http://localhost:8000",
      "description": "Local corpus",
      "auth": null
    }
  ]
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `alcove_manifest_version` | `"1"` | yes | Schema version. Currently only `"1"` is valid. |
| `registries` | object | no | Registry URLs. Defaults are the canonical Alcove registries. Omit to use defaults. |
| `registries.plugins` | string (URL) | no | Plugin registry endpoint. |
| `registries.indexes` | string (URL) | no | Index registry endpoint. |
| `plugins` | array | no | Plugins installed for this instance. |
| `plugins[].name` | string | yes | Package name (e.g. `alcove-audio`). |
| `plugins[].version` | string | no | PEP 440 version specifier (e.g. `>=0.2.0`, `==1.0.0`). |
| `plugins[].source` | `"registry"` \| `"local"` \| `"git"` | no | Where to install from. Default: `"registry"`. |
| `plugins[].url` | string | no | Required when `source` is `"git"` or `"local"`. |
| `indexes` | array | no | Index endpoints configured for this instance. |
| `indexes[].id` | string | yes | Local identifier. Used in CLI (`alcove query --index local`). |
| `indexes[].url` | string | yes | Base URL of the Alcove index endpoint. |
| `indexes[].description` | string | no | Human-readable label. |
| `indexes[].auth` | object \| null | no | Authentication config. See [Authentication](#authentication). |

### Authentication

Alcove's boundary rule — no auth in the plugin system — extends to indexes. The manifest can carry auth config for index endpoints, but the auth layer itself (token acquisition, refresh) lives outside the Alcove runtime.

```json
{
  "auth": {
    "type": "bearer",
    "token_env": "MYINDEX_TOKEN"
  }
}
```

Supported auth types:

| Type | Fields | Description |
|------|--------|-------------|
| `"bearer"` | `token_env` | Read token from named env var; send as `Authorization: Bearer <token>`. |
| `"basic"` | `user_env`, `password_env` | HTTP Basic Auth from env vars. |
| `null` | — | No auth (default). Safe for localhost-only indexes. |

---

## Registry JSON format

The registry endpoint returns a JSON document listing available items. Both the plugin registry and index registry use the same envelope.

### Plugin registry (`registry.json`)

```json
{
  "alcove_registry_version": "1",
  "updated": "2026-03-21T00:00:00Z",
  "plugins": [
    {
      "name": "alcove-audio",
      "version": "0.3.1",
      "description": "Audio transcription and semantic audio search via faster-whisper and CLAP.",
      "author": "Jane Doe",
      "license": "Apache-2.0",
      "homepage": "https://github.com/jdoe/alcove-audio",
      "entry_points": {
        "alcove.extractors": ["mp3", "wav", "m4a", "flac"],
        "alcove.embedders": [],
        "alcove.backends": []
      },
      "requires_network": false,
      "local_only": true,
      "tags": ["audio", "transcription", "bioacoustics"]
    }
  ]
}
```

#### Plugin registry fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Package name. Must be unique in the registry. |
| `version` | string | Latest published version. |
| `description` | string | One-line description. |
| `entry_points` | object | Which extension groups the plugin populates. |
| `requires_network` | bool | True if the plugin makes outbound calls (e.g. OpenAI embedder). |
| `local_only` | bool | True if the plugin preserves Alcove's offline-by-default guarantee. |
| `tags` | string[] | Free-form taxonomy for browsing. |

`requires_network: false` + `local_only: true` is the baseline. Cloud plugins (OpenAI embedder, Pinecone backend) must declare `requires_network: true, local_only: false`.

### Index registry (`registry.json`)

```json
{
  "alcove_registry_version": "1",
  "updated": "2026-03-21T00:00:00Z",
  "indexes": [
    {
      "id": "alcove-demo",
      "name": "Alcove Demo Corpus",
      "description": "A small public demo corpus for testing Alcove queries.",
      "url": "https://demo.alcove.software",
      "auth_required": false,
      "curator": "alcove",
      "document_count": 142,
      "tags": ["demo", "public"],
      "requires_plugin": null
    }
  ]
}
```

#### Index registry fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable identifier. Operators import this into `alcove.json` `indexes[].id`. |
| `name` | string | Display name. |
| `url` | string | Base URL of the index endpoint. |
| `auth_required` | bool | Whether access requires auth config. |
| `curator` | string | Who maintains this index. |
| `document_count` | int | Approximate corpus size. |
| `requires_plugin` | string \| null | Plugin name required to query this index type, if any. |

---

## Design rationale

### Can a plugin be an index source?

No — they are orthogonal primitives.

A **plugin** provides a mechanism: a callable that extracts text from a file extension, embeds text, or stores/queries vectors. A **plugin** is installed and registered via Python entry points.

An **index** is a pointer to a specific corpus endpoint: a URL, auth config, and metadata about what's there. An index might *require* a plugin to operate (e.g., a specialized backend plugin to query a non-standard vector store), but an index is not a plugin. The `requires_plugin` field in the index registry covers this dependency.

Conflating the two would break the orthogonality that makes Alcove composable. Keep them separate.

### Why a manifest file instead of env vars?

Env vars work for single-field overrides (`EMBEDDER`, `VECTOR_BACKEND`). A manifest handles structured configuration — arrays of plugins, multiple named index endpoints, auth per-index — without requiring a dozen env vars. The manifest is optional: Alcove works without one, using canonical defaults.

### Why `alcove_manifest_version: "1"` as a string?

Future versions may introduce breaking changes to the schema. A string version field in the document root allows parsers to reject unknown versions without guessing. Integer versions in JSON schemas have caused ambiguity (1 vs 1.0 vs "1"); string is unambiguous.

### Registry hosting

The canonical registries (`plugins.alcove.software`, `search.alcove.software`) are JSON files served over HTTPS — no dynamic server required. A static host (GitHub Pages, Cloudflare Pages, Netlify) is sufficient. The gate condition for creating these repos:

> **Don't create the repos until there's real curation work happening** — enough plugins/indexes that a dedicated repo formalizes something meaningful rather than just housing a list of 3 items.

Until that threshold, the canonical URLs can 404 gracefully; the runtime falls back to local-only operation.

---

## Runtime behavior

On startup, if `alcove.json` is present:

1. Read and validate against this schema. Warn on unknown fields; error on invalid types.
2. Merge configured plugins with installed Python packages. Plugins declared in `plugins[]` but not installed produce a warning with an install hint.
3. Make configured indexes available in the query API under their `id`. `alcove query --index <id>` routes to the matching URL.
4. Registry URLs are used only for `alcove plugins browse` and `alcove indexes browse` — not at startup. Discovery is opt-in.

If `alcove.json` is absent, the runtime behaves as today: entry-point plugin discovery, localhost index only.

---

## JSON Schema

The normative JSON Schema is at [`docs/alcove.schema.json`](alcove.schema.json). Editors that support `$schema` will validate `alcove.json` in place.
