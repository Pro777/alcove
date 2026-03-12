from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Iterable

from alcove.index.backend import get_backend
from alcove.index.embedder import get_embedder

MIRRULATIONS_COLLECTION = "mirrulations_docs"
TAG_STRIPPER = re.compile(r"<[^>]+>")
WHITESPACE = re.compile(r"\s+")


def ingest_mirrulations(
    source: str | Path | None = None,
    *,
    agencies: Iterable[str] | None = None,
    collection_name: str = MIRRULATIONS_COLLECTION,
    jsonl_out: str | Path | None = None,
) -> int:
    records = load_mirrulations_records(source=source, agencies=agencies)
    if jsonl_out is not None:
        write_jsonl(_apply_collection_name(records, collection_name=collection_name), jsonl_out)
    return index_mirrulations_records(records, collection_name=collection_name)


def load_mirrulations_records(
    source: str | Path | None = None,
    *,
    agencies: Iterable[str] | None = None,
) -> list[dict]:
    if not source:
        raise ValueError("Provide a local Mirrulations directory path.")

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(path)

    agency_filter = {item.strip().upper() for item in (agencies or []) if item and item.strip()}
    records: list[dict] = []
    for text_dir in _discover_text_directories(path, agency_filter=agency_filter):
        records.extend(_load_text_directory(text_dir))
    return records


def index_mirrulations_records(
    records: Iterable[dict],
    *,
    collection_name: str = MIRRULATIONS_COLLECTION,
) -> int:
    materialized = _apply_collection_name(records, collection_name=collection_name)
    if not materialized:
        return 0

    embedder = get_embedder()
    backend = get_backend(embedder, collection_name=collection_name)
    documents = [record["document"] for record in materialized]
    backend.add(
        ids=[record["id"] for record in materialized],
        embeddings=embedder.embed(documents),
        documents=documents,
        metadatas=[record["metadata"] for record in materialized],
    )
    return len(materialized)


def write_jsonl(records: Iterable[dict], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return output_path


def _apply_collection_name(records: Iterable[dict], *, collection_name: str) -> list[dict]:
    normalized = []
    for record in records:
        metadata = dict(record["metadata"])
        metadata["collection"] = collection_name
        normalized.append(
            {
                "id": record["id"],
                "document": record["document"],
                "metadata": metadata,
            }
        )
    return normalized


def _discover_text_directories(path: Path, *, agency_filter: set[str]) -> list[Path]:
    if path.is_dir() and path.name.startswith("text-"):
        candidates = [path]
    else:
        candidates = [candidate for candidate in path.rglob("text-*") if candidate.is_dir()]

    discovered = []
    for candidate in sorted(candidates):
        agency = _agency_for_text_dir(candidate)
        if agency_filter and agency.upper() not in agency_filter:
            continue
        discovered.append(candidate)
    return discovered


def _load_text_directory(text_dir: Path) -> list[dict]:
    docket_id = text_dir.name.removeprefix("text-")
    agency = _agency_for_text_dir(text_dir)
    records: list[dict] = []

    docket_dir = text_dir / "docket"
    docket_json = docket_dir / f"{docket_id}.json"
    if docket_json.exists():
        record = _build_docket_record(docket_json, agency=agency, docket_id=docket_id)
        if record:
            records.append(record)

    records.extend(_load_document_records(text_dir, agency=agency, docket_id=docket_id))
    records.extend(_load_comment_records(text_dir, agency=agency, docket_id=docket_id))
    records.extend(_load_attachment_records(text_dir, agency=agency, docket_id=docket_id, scope="documents"))
    records.extend(_load_attachment_records(text_dir, agency=agency, docket_id=docket_id, scope="comments"))
    return records


def _load_document_records(text_dir: Path, *, agency: str, docket_id: str) -> list[dict]:
    directory = text_dir / "documents"
    records: list[dict] = []
    for json_path in sorted(directory.glob("*.json")):
        payload = _read_json(json_path)
        document_id = _extract_entity_id(payload, fallback=json_path.stem)
        attributes = _extract_attributes(payload)
        title = _first_nonempty(
            _clean_text(attributes.get("title")),
            _clean_text(attributes.get("objectTitle")),
            document_id,
        )
        html_path = directory / f"{json_path.stem}_content.htm"
        body = _first_nonempty(
            _clean_text(html_path.read_text(encoding="utf-8", errors="ignore")) if html_path.exists() else "",
            _clean_text(attributes.get("summary")),
            _clean_text(attributes.get("abstract")),
        )
        if not body:
            continue

        records.append(
            {
                "id": f"document-{document_id}",
                "document": _compose_record_text(title, body),
                "metadata": {
                    "source": str(json_path),
                    "agency": agency,
                    "docket_id": docket_id,
                    "mirrulations_id": document_id,
                    "entry_type": "document",
                    "title": title,
                    "document_type": _first_nonempty(attributes.get("documentType"), attributes.get("category"), ""),
                    "posted_date": _first_nonempty(attributes.get("postedDate"), attributes.get("modifyDate"), ""),
                    "url": _regulations_url(document_id, entry_type="document"),
                    "source_format": "mirrulations-document-json",
                },
            }
        )
    return records


def _load_comment_records(text_dir: Path, *, agency: str, docket_id: str) -> list[dict]:
    directory = text_dir / "comments"
    records: list[dict] = []
    for json_path in sorted(directory.glob("*.json")):
        payload = _read_json(json_path)
        comment_id = _extract_entity_id(payload, fallback=json_path.stem)
        attributes = _extract_attributes(payload)
        body = _first_nonempty(
            _clean_text(attributes.get("comment")),
            _clean_text(attributes.get("commentText")),
        )
        if not body:
            continue

        title = _first_nonempty(
            _clean_text(attributes.get("title")),
            _clean_text(attributes.get("organization")),
            comment_id,
        )
        records.append(
            {
                "id": f"comment-{comment_id}",
                "document": _compose_record_text(title, body),
                "metadata": {
                    "source": str(json_path),
                    "agency": agency,
                    "docket_id": docket_id,
                    "mirrulations_id": comment_id,
                    "entry_type": "comment",
                    "title": title,
                    "comment_on": attributes.get("commentOn") or "",
                    "posted_date": _first_nonempty(attributes.get("postedDate"), attributes.get("modifyDate"), ""),
                    "url": _regulations_url(comment_id, entry_type="document"),
                    "source_format": "mirrulations-comment-json",
                },
            }
        )
    return records


def _load_attachment_records(text_dir: Path, *, agency: str, docket_id: str, scope: str) -> list[dict]:
    records: list[dict] = []
    extracted_root = text_dir / f"{scope}_extracted_text"
    if not extracted_root.exists():
        return records

    scope_name = "document" if scope == "documents" else "comment"
    for tool_dir in sorted(path for path in extracted_root.iterdir() if path.is_dir()):
        for txt_path in sorted(tool_dir.glob("*.txt")):
            body = _clean_text(txt_path.read_text(encoding="utf-8", errors="ignore"))
            if not body:
                continue

            parent_id = _parent_id_for_attachment(txt_path.stem)
            title = f"{parent_id} attachment text"
            records.append(
                {
                    "id": f"attachment-{scope_name}-{txt_path.stem}",
                    "document": _compose_record_text(title, body),
                    "metadata": {
                        "source": str(txt_path),
                        "agency": agency,
                        "docket_id": docket_id,
                        "mirrulations_id": txt_path.stem,
                        "entry_type": "attachment",
                        "attachment_scope": scope_name,
                        "parent_id": parent_id,
                        "extraction_tool": tool_dir.name,
                        "title": title,
                        "url": _regulations_url(parent_id, entry_type="document"),
                        "source_format": f"mirrulations-{scope_name}-attachment-text",
                    },
                }
            )
    return records


def _build_docket_record(json_path: Path, *, agency: str, docket_id: str) -> dict | None:
    payload = _read_json(json_path)
    attributes = _extract_attributes(payload)
    title = _first_nonempty(_clean_text(attributes.get("title")), docket_id)
    body = _first_nonempty(
        _clean_text(attributes.get("summary")),
        _clean_text(attributes.get("description")),
        _clean_text(attributes.get("keywords")),
        title,
    )
    if not body:
        return None

    return {
        "id": f"docket-{docket_id}",
        "document": _compose_record_text(title, body),
        "metadata": {
            "source": str(json_path),
            "agency": agency,
            "docket_id": docket_id,
            "mirrulations_id": docket_id,
            "entry_type": "docket",
            "title": title,
            "posted_date": _first_nonempty(attributes.get("postedDate"), attributes.get("modifyDate"), ""),
            "url": _regulations_url(docket_id, entry_type="docket"),
            "source_format": "mirrulations-docket-json",
        },
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))


def _extract_attributes(payload: dict) -> dict:
    if isinstance(payload.get("data"), dict):
        attributes = payload["data"].get("attributes")
        if isinstance(attributes, dict):
            return attributes
    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        return attributes
    return {}


def _extract_entity_id(payload: dict, *, fallback: str) -> str:
    if isinstance(payload.get("data"), dict):
        value = payload["data"].get("id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = payload.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _agency_for_text_dir(text_dir: Path) -> str:
    try:
        return text_dir.parent.parent.name
    except IndexError:
        return "UNKNOWN"


def _regulations_url(entry_id: str, *, entry_type: str) -> str:
    base = "https://www.regulations.gov"
    if entry_type == "docket":
        return f"{base}/docket/{entry_id}"
    return f"{base}/document/{entry_id}"


def _parent_id_for_attachment(stem: str) -> str:
    for suffix in ("_content_extracted", "_extracted"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    if "_attachment_" in stem:
        return stem.split("_attachment_", 1)[0]
    if stem.endswith("_content"):
        return stem[: -len("_content")]
    return stem


def _compose_record_text(title: str, body: str) -> str:
    title = _clean_text(title)
    body = _clean_text(body)
    if title and body and body != title:
        return f"{title}\n\n{body}"
    return title or body


def _first_nonempty(*values: str | None) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ""


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = unescape(str(value))
    text = TAG_STRIPPER.sub(" ", text)
    return WHITESPACE.sub(" ", text).strip()
