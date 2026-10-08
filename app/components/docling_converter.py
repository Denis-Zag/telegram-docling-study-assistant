"""Компонент преобразования и структурного разбиения документов через Docling."""

from __future__ import annotations

import hashlib
from pathlib import Path

from docling.chunking import HierarchicalChunker
from docling.document_converter import DocumentConverter
from haystack import Document, component


class DocumentConversionError(RuntimeError):
    """Документ не удалось преобразовать в пригодные для поиска чанки."""


@component
class DoclingDocumentConverter:
    """Преобразовать PDF/DOCX и вернуть структурные чанки Haystack."""

    def __init__(self) -> None:
        self._converter = DocumentConverter()
        self._chunker = HierarchicalChunker()

    @component.output_types(documents=list[Document], summary_text=str)
    def run(
        self,
        file_path: str,
        original_name: str,
        document_id: str,
    ) -> dict[str, list[Document] | str]:
        """Распознать документ, извлечь структуру и подготовить метаданные."""

        path = Path(file_path)
        if not path.is_file():
            raise DocumentConversionError("Файл для обработки не найден.")

        converted = self._converter.convert(path).document
        documents: list[Document] = []

        for chunk_index, chunk in enumerate(self._chunker.chunk(dl_doc=converted)):
            content = self._chunker.contextualize(chunk).strip()
            if not content:
                continue

            page_numbers = sorted(
                {
                    int(provenance.page_no)
                    for item in (chunk.meta.doc_items or [])
                    for provenance in (item.prov or [])
                    if getattr(provenance, "page_no", None) is not None
                }
            )
            headings = [
                heading.strip()
                for heading in (chunk.meta.headings or [])
                if heading.strip()
            ]
            raw_id = f"{document_id}:{chunk_index}"
            documents.append(
                Document(
                    id=hashlib.sha256(raw_id.encode("utf-8")).hexdigest(),
                    content=content,
                    meta={
                        "type": "study_document",
                        "document_id": document_id,
                        "file_name": original_name,
                        "chunk_index": chunk_index,
                        "page_numbers": ",".join(str(number) for number in page_numbers),
                        "heading": " > ".join(headings),
                    },
                )
            )

        if not documents:
            raise DocumentConversionError("Docling не извлёк текст из документа.")

        summary_text = "\n\n".join(document.content or "" for document in documents)
        return {
            "documents": documents,
            "summary_text": summary_text[:12_000],
        }
