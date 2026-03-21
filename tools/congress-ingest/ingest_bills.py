#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence
from urllib import error, parse, request

from defusedxml import ElementTree as ET

COLLECTION_NAME = "congress_summaries"
DEFAULT_BILL_TYPES = (
    "hr",
    "s",
    "hjres",
    "sjres",
    "hres",
    "sres",
    "hconres",
    "sconres",
)
AVAILABLE_CONGRESSES = tuple(range(113, 120))
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
SUMMARY_ID_RE = re.compile(
    r"^id(?P<congress>\d+)(?P<bill_type>[a-z]+)(?P<bill_number>\d+)(?P<version>v\d+)$",
    re.IGNORECASE,
)
BUNDLE_FILE_RE = re.compile(
    r"^BILLSUM-(?P<congress>\d+)(?P<bill_type>[a-z]+)(?P<bill_number>\d+)\.xml$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class SourceBlob:
    key: str
    source_name: str
    payload: bytes
    source_url: str | None = None


@dataclass(slots=True)
class BillSummaryChunk:
    id: str
    text: str
    metadata: dict[str, object]


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.completed_files = self._load()

    def _load(self) -> set[str]:
        if not self.path.exists():
            return set()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return set(payload.get("completed_files", []))

    def contains(self, key: str) -> bool:
        return key in self.completed_files

    def mark_completed(self, key: str) -> None:
        self.completed_files.add(key)
        self.save()

    def reset(self) -> None:
        self.completed_files = set()
        if self.path.exists():
            self.path.unlink()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"completed_files": sorted(self.completed_files)}
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_congresses(value: str) -> list[int]:
    if value == "all":
        return list(AVAILABLE_CONGRESSES)
    try:
        return [int(value)]
    except ValueError as exc:
        raise ValueError("--congress must be an integer or 'all'") from exc


def default_state_path(chroma_path: Path) -> Path:
    return chroma_path.parent / "billsum_ingest_state.json"


def build_bundle_url(congress: int, bill_type: str) -> str:
    return f"https://www.govinfo.gov/bulkdata/BILLSUM/{congress}/{bill_type}/BILLSUM-{congress}-{bill_type}.zip"


def build_bill_xml_url(congress: int, bill_type: str, bill_number: int) -> str:
    return f"https://www.govinfo.gov/bulkdata/BILLSUM/{congress}/{bill_type}/BILLSUM-{congress}{bill_type}{bill_number}.xml"


def build_bill_details_url(congress: int, bill_type: str, bill_number: int) -> str:
    return f"https://www.govinfo.gov/app/details/BILLSUM-{congress}{bill_type}{bill_number}"


def strip_html(fragment: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", fragment or ""))
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_summary_identity(
    summary_id: str | None,
    *,
    congress: int,
    bill_type: str,
    bill_number: int,
) -> tuple[str, str]:
    version_code = "v00"
    if summary_id:
        match = SUMMARY_ID_RE.match(summary_id)
        if match:
            congress = int(match.group("congress"))
            bill_type = match.group("bill_type").lower()
            bill_number = int(match.group("bill_number"))
            version_code = match.group("version").lower()
        else:
            version_match = re.search(r"(v\d+)$", summary_id, re.IGNORECASE)
            if version_match:
                version_code = version_match.group(1).lower()
    normalized = f"billsum-{congress}-{bill_type}-{bill_number}-{version_code}"
    return normalized, version_code


def version_sort_key(version_code: str) -> tuple[int, str]:
    match = re.match(r"^v(\d+)$", version_code or "", re.IGNORECASE)
    if not match:
        return -1, (version_code or "").lower()
    return int(match.group(1)), version_code.lower()


def mark_latest(chunks: list[BillSummaryChunk]) -> None:
    if not chunks:
        return
    latest = max(
        chunks,
        key=lambda chunk: (
            *version_sort_key(str(chunk.metadata.get("version_code", ""))),
            str(chunk.metadata.get("action_date", "")),
        ),
    )
    for chunk in chunks:
        chunk.metadata["is_latest"] = chunk.id == latest.id


def parse_billsum_xml(
    payload: bytes | str,
    *,
    source_name: str,
    source_url: str | None = None,
) -> list[BillSummaryChunk]:
    root = ET.fromstring(payload if isinstance(payload, bytes) else payload.encode("utf-8"))
    chunks: list[BillSummaryChunk] = []

    for item in root.findall("item"):
        congress_text = (item.attrib.get("congress") or "0").strip()
        bill_type = (item.attrib.get("measure-type") or "").strip().lower()
        bill_number_text = (item.attrib.get("measure-number") or "0").strip()
        if not congress_text.isdigit() or not bill_type or not bill_number_text.isdigit():
            continue

        congress = int(congress_text)
        bill_number = int(bill_number_text)
        title = (item.findtext("title") or "").strip()
        origin_chamber = (item.attrib.get("originChamber") or "").strip().upper()
        publish_date = (item.attrib.get("orig-publish-date") or "").strip()
        update_date = (item.attrib.get("update-date") or "").strip()

        item_chunks: list[BillSummaryChunk] = []
        for summary in item.findall("summary"):
            summary_id_attr = (summary.attrib.get("summary-id") or "").strip()
            normalized_id, version_code = normalize_summary_identity(
                summary_id_attr,
                congress=congress,
                bill_type=bill_type,
                bill_number=bill_number,
            )
            action_date = (summary.findtext("action-date") or "").strip()
            action_desc = (summary.findtext("action-desc") or "").strip()
            chamber = (summary.attrib.get("currentChamber") or "BOTH").strip().upper()
            summary_text_node = summary.find("summary-text")
            raw_summary = ""
            if summary_text_node is not None:
                raw_summary = "".join(summary_text_node.itertext())
            clean_summary = strip_html(raw_summary)
            if not clean_summary:
                continue
            metadata = {
                "congress": congress,
                "bill_type": bill_type,
                "bill_number": bill_number,
                "version_code": version_code,
                "chamber": chamber,
                "action_date": action_date,
                "action_desc": action_desc,
                "title": title,
                "origin_chamber": origin_chamber,
                "publish_date": publish_date,
                "update_date": update_date,
                "url": build_bill_details_url(congress, bill_type, bill_number),
                "is_latest": False,
            }
            item_chunks.append(BillSummaryChunk(id=normalized_id, text=clean_summary, metadata=metadata))

        mark_latest(item_chunks)
        chunks.extend(item_chunks)

    return chunks


def fetch_url_bytes(url: str, *, timeout: int = 60, retries: int = 4, backoff: float = 1.0) -> bytes:
    parsed_scheme = parse.urlparse(url).scheme
    if parsed_scheme != "https":
        raise ValueError(f"fetch_url_bytes requires an https URL, got scheme {parsed_scheme!r}")
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        req = request.Request(url, headers={"User-Agent": "alcove-billsum-ingest/0.1"})
        try:
            with request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except error.HTTPError as exc:
            if exc.code == 404:
                raise
            last_error = exc
        except error.URLError as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(backoff * (2 ** (attempt - 1)))
    if last_error is None:
        raise RuntimeError(f"Failed to download {url}")
    raise RuntimeError(f"Failed to download {url}: {last_error}") from last_error


def discover_remote_sources(
    congresses: Sequence[int],
    bill_types: Sequence[str],
    *,
    timeout: int,
    retries: int,
    stream=sys.stdout,
) -> list[SourceBlob]:
    sources: list[SourceBlob] = []
    for congress in congresses:
        for bill_type in bill_types:
            bundle_url = build_bundle_url(congress, bill_type)
            print(f"Fetching {bundle_url}", file=stream)
            try:
                bundle_bytes = fetch_url_bytes(bundle_url, timeout=timeout, retries=retries)
            except error.HTTPError as exc:
                if exc.code == 404:
                    print(f"Skipping {bundle_url} (404)", file=stream)
                    continue
                raise
            with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as bundle:
                names = sorted(name for name in bundle.namelist() if name.lower().endswith(".xml"))
                bundle_label = bundle_url.rsplit("/", 1)[-1]
                print(f"Found {len(names)} XML files in {bundle_label}", file=stream)
                for name in names:
                    file_name = Path(name).name
                    match = BUNDLE_FILE_RE.match(file_name)
                    if match:
                        source_key = (
                            f"{match.group('congress')}/"
                            f"{match.group('bill_type').lower()}/"
                            f"{file_name}"
                        )
                        source_url = build_bill_xml_url(
                            int(match.group("congress")),
                            match.group("bill_type").lower(),
                            int(match.group("bill_number")),
                        )
                    else:
                        source_key = f"{congress}/{bill_type}/{file_name}"
                        source_url = None
                    sources.append(
                        SourceBlob(
                            key=source_key,
                            source_name=file_name,
                            payload=bundle.read(name),
                            source_url=source_url,
                        )
                    )
    return sources


def load_source_from_path(path: Path) -> list[SourceBlob]:
    if path.suffix.lower() == ".xml":
        return [
            SourceBlob(
                key=str(path.resolve()),
                source_name=path.name,
                payload=path.read_bytes(),
                source_url=None,
            )
        ]
    if path.suffix.lower() == ".zip":
        sources: list[SourceBlob] = []
        with zipfile.ZipFile(path) as bundle:
            for name in sorted(item for item in bundle.namelist() if item.lower().endswith(".xml")):
                sources.append(
                    SourceBlob(
                        key=f"{path.resolve()}::{name}",
                        source_name=Path(name).name,
                        payload=bundle.read(name),
                        source_url=None,
                    )
                )
        return sources
    raise ValueError(f"Unsupported source path: {path}")


def discover_local_sources(paths: Sequence[str | Path]) -> list[SourceBlob]:
    sources: list[SourceBlob] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in {".xml", ".zip"}:
                    sources.extend(load_source_from_path(child))
            continue
        sources.extend(load_source_from_path(path))
    return sources


class OllamaEmbedder:
    def __init__(
        self,
        *,
        base_url: str,
        model: str = "nomic-embed-text",
        timeout: int = 60,
        retries: int = 4,
    ):
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"Ollama base_url must use http or https scheme, got: {base_url!r}"
            )
        self.endpoint = base_url.rstrip("/") + "/api/embeddings"
        self.model = model
        self.timeout = timeout
        self.retries = retries

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        payload = json.dumps({"model": self.model, "prompt": text or " "}).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            req = request.Request(
                self.endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "alcove-billsum-ingest/0.1",
                },
            )
            try:
                with request.urlopen(req, timeout=self.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                embedding = body.get("embedding")
                if not isinstance(embedding, list):
                    raise RuntimeError(f"Unexpected Ollama response: {body}")
                return embedding
            except (error.HTTPError, error.URLError, RuntimeError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(2 ** (attempt - 1))
        raise RuntimeError(f"Failed to embed text via Ollama: {last_error}") from last_error


class ChromaWriter:
    def __init__(self, path: Path, *, collection_name: str = COLLECTION_NAME):
        import chromadb
        from chromadb.config import Settings

        self.path = path
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(
            path=str(path),
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def reset(self) -> None:
        try:
            self.client.delete_collection(name=self.collection_name)
        except ValueError:
            pass
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def upsert(self, chunks: Sequence[BillSummaryChunk], embeddings: Sequence[Sequence[float]]) -> None:
        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[chunk.metadata for chunk in chunks],
            embeddings=[list(vector) for vector in embeddings],
        )


def process_sources(
    sources: Sequence[SourceBlob],
    *,
    state: StateStore,
    dry_run: bool,
    writer: ChromaWriter | None = None,
    embedder: OllamaEmbedder | None = None,
    stream=sys.stdout,
) -> dict[str, int]:
    stats = {"processed": 0, "skipped": 0, "failed": 0, "summaries": 0}
    total = len(sources)

    for index, source in enumerate(sources, start=1):
        if state.contains(source.key):
            stats["skipped"] += 1
            print(f"[{index}/{total}] Skipped {source.source_name} (already ingested)", file=stream)
            continue

        try:
            chunks = parse_billsum_xml(source.payload, source_name=source.source_name, source_url=source.source_url)
            if not dry_run:
                if writer is None or embedder is None:
                    raise RuntimeError("writer and embedder are required unless --dry-run is set")
                if chunks:
                    embeddings = embedder.embed_documents([chunk.text for chunk in chunks])
                    writer.upsert(chunks, embeddings)
                state.mark_completed(source.key)
            stats["processed"] += 1
            stats["summaries"] += len(chunks)
            verb = "Parsed" if dry_run else "Ingested"
            print(f"[{index}/{total}] {verb} {source.source_name} ({len(chunks)} summaries)", file=stream)
        except (ValueError, RuntimeError, OSError) as exc:
            stats["failed"] += 1
            print(f"[{index}/{total}] Failed {source.source_name}: {exc}", file=stream)

    suffix = " (dry-run)" if dry_run else ""
    print(
        f"Completed: {stats['processed']} processed, {stats['skipped']} skipped, "
        f"{stats['failed']} failed, {stats['summaries']} summaries{suffix}.",
        file=stream,
    )
    return stats


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resumable GovInfo BillSum ingest into local ChromaDB.")
    parser.add_argument("--congress", default="118", help="Congress number or 'all' for 113-119")
    parser.add_argument("--resume", action="store_true", default=True, help="Resume from local state (default)")
    parser.add_argument("--fresh", action="store_true", help="Clear ingest state and rebuild collection")
    parser.add_argument("--dry-run", action="store_true", help="Parse and count only, do not embed or store")
    parser.add_argument(
        "--chroma-path",
        default=os.environ.get("BILLSUM_CHROMA_PATH", "./data/chroma"),
        help="Persistent ChromaDB path",
    )
    parser.add_argument("--state-path", default=None, help="Optional JSON state file path")
    parser.add_argument(
        "--ollama-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        help="Base URL for the local Ollama API",
    )
    parser.add_argument(
        "--bill-type",
        action="append",
        choices=DEFAULT_BILL_TYPES,
        help="Limit ingest to one or more bill types",
    )
    parser.add_argument(
        "--source-path",
        action="append",
        help="Optional local XML, ZIP, or directory path to parse instead of downloading GovInfo bundles",
    )
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds")
    parser.add_argument("--retries", type=int, default=4, help="HTTP retry count")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        congresses = parse_congresses(args.congress)
    except ValueError as exc:
        parser.error(str(exc))

    bill_types = tuple(args.bill_type or DEFAULT_BILL_TYPES)
    chroma_path = Path(args.chroma_path)
    state_path = Path(args.state_path) if args.state_path else default_state_path(chroma_path)
    state = StateStore(state_path)

    if args.fresh and args.dry_run:
        parser.error("--fresh cannot be used with --dry-run")

    writer: ChromaWriter | None = None
    if args.fresh:
        state.reset()
    if not args.dry_run:
        writer = ChromaWriter(chroma_path)
        if args.fresh:
            writer.reset()

    if args.source_path:
        sources = discover_local_sources(args.source_path)
    else:
        sources = discover_remote_sources(
            congresses,
            bill_types,
            timeout=args.timeout,
            retries=args.retries,
            stream=sys.stdout,
        )

    print(f"Discovered {len(sources)} source files.", file=sys.stdout)

    embedder = None if args.dry_run else OllamaEmbedder(
        base_url=args.ollama_url,
        timeout=args.timeout,
        retries=args.retries,
    )
    stats = process_sources(
        sources,
        state=state,
        dry_run=args.dry_run,
        writer=writer,
        embedder=embedder,
        stream=sys.stdout,
    )
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
