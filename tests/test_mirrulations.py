from __future__ import annotations

import json

from alcove.mirrulations import (
    MIRRULATIONS_COLLECTION,
    ingest_mirrulations,
    index_mirrulations_records,
    load_mirrulations_records,
)


def test_load_mirrulations_records_normalizes_text_tree(tmp_path):
    text_dir = _make_text_tree(tmp_path, agency="EPA", docket_id="EPA-HQ-OAR-2023-0534")

    records = load_mirrulations_records(text_dir.parent.parent)

    assert len(records) == 5
    ids = {record["id"] for record in records}
    assert "docket-EPA-HQ-OAR-2023-0534" in ids
    assert "document-EPA-HQ-OAR-2023-0534-0001" in ids
    assert "comment-EPA-HQ-OAR-2023-0534-0002" in ids
    assert "attachment-document-EPA-HQ-OAR-2023-0534-0001_content_extracted" in ids
    assert "attachment-comment-EPA-HQ-OAR-2023-0534-0002_attachment_1_extracted" in ids

    comment = next(record for record in records if record["metadata"]["entry_type"] == "comment")
    assert "This proposal improves public health." in comment["document"]
    assert "<p>" not in comment["document"]
    assert comment["metadata"]["agency"] == "EPA"
    assert comment["metadata"]["docket_id"] == "EPA-HQ-OAR-2023-0534"


def test_load_mirrulations_records_filters_agencies(tmp_path):
    _make_text_tree(tmp_path, agency="EPA", docket_id="EPA-HQ-OAR-2023-0534")
    _make_text_tree(tmp_path, agency="SEC", docket_id="SEC-2024-0007")

    records = load_mirrulations_records(tmp_path, agencies=["EPA"])

    assert records
    assert all(record["metadata"]["agency"] == "EPA" for record in records)


def test_index_mirrulations_records_tags_requested_collection(monkeypatch):
    captured = {}

    class DummyEmbedder:
        def embed(self, texts):
            captured["embedded"] = list(texts)
            return [[0.125, 0.25] for _ in texts]

    class DummyBackend:
        def add(self, ids, embeddings, documents, metadatas):
            captured["ids"] = ids
            captured["embeddings"] = embeddings
            captured["documents"] = documents
            captured["metadatas"] = metadatas

    monkeypatch.setattr("alcove.mirrulations.get_embedder", lambda: DummyEmbedder())
    monkeypatch.setattr("alcove.mirrulations.get_backend", lambda embedder: DummyBackend())

    records = [
        {
            "id": "comment-EPA-HQ-OAR-2023-0534-0002",
            "document": "EPA comment\n\nThis proposal improves public health.",
            "metadata": {
                "collection": MIRRULATIONS_COLLECTION,
                "source": "comment.json",
                "entry_type": "comment",
            },
        }
    ]
    indexed = index_mirrulations_records(records)

    assert indexed == 1
    assert captured["ids"] == ["comment-EPA-HQ-OAR-2023-0534-0002"]
    assert captured["metadatas"][0]["collection"] == MIRRULATIONS_COLLECTION


def test_ingest_mirrulations_writes_requested_collection_to_jsonl(tmp_path, monkeypatch):
    text_dir = _make_text_tree(tmp_path, agency="EPA", docket_id="EPA-HQ-OAR-2023-0534")
    output_path = tmp_path / "mirrulations.jsonl"

    monkeypatch.setattr("alcove.mirrulations.index_mirrulations_records", lambda records: len(list(records)))
    indexed = ingest_mirrulations(
        source=text_dir.parent.parent,
        collection_name="regulatory_test_docs",
        jsonl_out=output_path,
    )

    payload = output_path.read_text(encoding="utf-8")
    assert indexed == 5
    assert "regulatory_test_docs" in payload
    assert "EPA-HQ-OAR-2023-0534" in payload


def _make_text_tree(root, *, agency: str, docket_id: str):
    text_dir = root / agency / docket_id / f"text-{docket_id}"
    (text_dir / "docket").mkdir(parents=True)
    (text_dir / "documents").mkdir(parents=True)
    (text_dir / "comments").mkdir(parents=True)
    (text_dir / "documents_extracted_text" / "pikepdf").mkdir(parents=True)
    (text_dir / "comments_extracted_text" / "pikepdf").mkdir(parents=True)

    _write_json(
        text_dir / "docket" / f"{docket_id}.json",
        {
            "data": {
                "id": docket_id,
                "attributes": {
                    "title": "Power Plant Emissions Rule",
                    "summary": "Proposal to reduce sulfur dioxide and particulate emissions.",
                },
            }
        },
    )
    _write_json(
        text_dir / "documents" / f"{docket_id}-0001.json",
        {
            "data": {
                "id": f"{docket_id}-0001",
                "attributes": {
                    "title": "Draft Rule Text",
                    "category": "Rule",
                    "postedDate": "2023-10-01",
                },
            }
        },
    )
    (text_dir / "documents" / f"{docket_id}-0001_content.htm").write_text(
        "<html><body><p>The proposed rule lowers emissions limits for coal plants.</p></body></html>",
        encoding="utf-8",
    )
    _write_json(
        text_dir / "comments" / f"{docket_id}-0002.json",
        {
            "data": {
                "id": f"{docket_id}-0002",
                "attributes": {
                    "organization": "Clean Air Alliance",
                    "comment": "<p>This proposal improves public health.</p>",
                    "modifyDate": "2023-10-12T14:17:51Z",
                },
            }
        },
    )
    (text_dir / "documents_extracted_text" / "pikepdf" / f"{docket_id}-0001_content_extracted.txt").write_text(
        "Attachment appendix with emissions tables.",
        encoding="utf-8",
    )
    (text_dir / "comments_extracted_text" / "pikepdf" / f"{docket_id}-0002_attachment_1_extracted.txt").write_text(
        "Attached epidemiology study supporting tighter particulate controls.",
        encoding="utf-8",
    )
    return text_dir


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
