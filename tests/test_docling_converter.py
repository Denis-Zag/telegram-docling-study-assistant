"""Проверки преобразования чанков Docling в документы Haystack."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.components.docling_converter import (
    DoclingDocumentConverter,
    DocumentConversionError,
)


class FakeConverter:
    def __init__(self, document: Any) -> None:
        self.document = document

    def convert(self, _path: Any) -> Any:
        return SimpleNamespace(document=self.document)


class FakeChunker:
    def __init__(self, chunks: list[Any]) -> None:
        self.chunks = chunks

    def chunk(self, *, dl_doc: Any) -> list[Any]:
        assert dl_doc == "docling-document"
        return self.chunks

    def contextualize(self, chunk: Any) -> str:
        return chunk.text


def make_component(chunks: list[Any]) -> DoclingDocumentConverter:
    converter = object.__new__(DoclingDocumentConverter)
    converter._converter = FakeConverter("docling-document")  # type: ignore[attr-defined]
    converter._chunker = FakeChunker(chunks)  # type: ignore[attr-defined]
    return converter


def test_converter_preserves_file_chunk_and_page_metadata(tmp_path: Any) -> None:
    source = tmp_path / "lesson.pdf"
    source.write_bytes(b"pdf")
    provenance = SimpleNamespace(page_no=3)
    item = SimpleNamespace(prov=[provenance])
    meta = SimpleNamespace(doc_items=[item], headings=["Раздел урока"])
    component = make_component([SimpleNamespace(text="  Текст урока  ", meta=meta)])

    result = component.run(str(source), "lesson.pdf", "document-hash")
    document = result["documents"][0]

    assert document.content == "Текст урока"
    assert document.meta == {
        "type": "study_document",
        "document_id": "document-hash",
        "file_name": "lesson.pdf",
        "chunk_index": 0,
        "page_numbers": "3",
        "heading": "Раздел урока",
    }
    assert result["summary_text"] == "Текст урока"


def test_converter_rejects_document_without_text(tmp_path: Any) -> None:
    source = tmp_path / "empty.docx"
    source.write_bytes(b"docx")
    component = make_component([])

    with pytest.raises(DocumentConversionError, match="не извлёк текст"):
        component.run(str(source), "empty.docx", "document-hash")


def test_converter_accepts_missing_headings_and_provenance(tmp_path: Any) -> None:
    source = tmp_path / "plain.docx"
    source.write_bytes(b"docx")
    item = SimpleNamespace(prov=None)
    meta = SimpleNamespace(doc_items=[item], headings=None)
    component = make_component([SimpleNamespace(text="Обычный текст", meta=meta)])

    result = component.run(str(source), "plain.docx", "document-hash")

    assert result["documents"][0].meta["page_numbers"] == ""
    assert result["documents"][0].meta["heading"] == ""
