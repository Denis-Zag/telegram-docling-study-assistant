"""Прикладная логика загрузки документов и ответов по ним."""

from __future__ import annotations

import hashlib
import re
import tempfile
import time
from pathlib import Path
from threading import Lock

from haystack import Document, Pipeline
from loguru import logger
from pinecone.errors.exceptions import PineconeTimeoutError

from app.config import Settings
from app.document_store import PineconeStoreRegistry
from app.models import DocumentProcessingResult, StudyReply
from app.pipelines.generation import build_generation_pipeline
from app.pipelines.ingestion import build_ingestion_pipeline

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


class UnsupportedDocumentError(ValueError):
    """Пользователь передал формат, не входящий в согласованный MVP."""


class StudyAssistantService:
    """Управлять пользовательскими пайплайнами и временными файлами."""

    def __init__(self, settings: Settings, stores: PineconeStoreRegistry) -> None:
        self._settings = settings
        self._stores = stores
        self._ingestion_pipelines: dict[str, Pipeline] = {}
        self._generation_pipelines: dict[str, Pipeline] = {}
        self._pipelines_lock = Lock()

    def process_document(
        self,
        *,
        user_id: int,
        file_name: str,
        content: bytes,
    ) -> DocumentProcessingResult:
        """Временно сохранить файл, выполнить ingestion pipeline и удалить оригинал."""

        safe_name = Path(file_name).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise UnsupportedDocumentError("Поддерживаются только файлы PDF и DOCX.")
        if not content:
            raise ValueError("Получен пустой файл.")

        document_id = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory(prefix="docling-study-") as temp_dir:
            temp_path = Path(temp_dir) / f"source{suffix}"
            temp_path.write_bytes(content)
            result = self._ingestion_pipeline(user_id).run(
                {
                    "converter": {
                        "file_path": str(temp_path),
                        "original_name": safe_name,
                        "document_id": document_id,
                    },
                    "summary_prompt": {"file_name": safe_name},
                }
            )

        chunks_written = int(result["writer"]["documents_written"])
        summary = result["summary_llm"]["replies"][0].text.strip()
        summary = _one_sentence(summary)
        logger.info(
            "Документ обработан user_namespace={} file_name={} chunks={}",
            self._stores.namespace_for(user_id),
            safe_name,
            chunks_written,
        )
        return DocumentProcessingResult(
            file_name=safe_name,
            chunks_written=chunks_written,
            summary=summary,
        )

    def answer(self, *, user_id: int, question: str) -> StudyReply:
        """Запустить generation pipeline и вернуть источники найденных фрагментов."""

        normalized_question = question.strip()
        if not normalized_question:
            return StudyReply(text="Напишите непустой вопрос.")

        result = self._run_answer_pipeline(
            user_id=user_id,
            question=normalized_question,
        )
        documents: list[Document] = result["retriever"]["documents"]
        raw_answer = result["llm"]["replies"][0].text.strip()
        answer, cited_documents = _extract_cited_documents(raw_answer, documents)
        if not answer:
            answer = "Не удалось сформировать ответ. Попробуйте уточнить вопрос."

        sources = tuple(
            dict.fromkeys(_source_label(document) for document in cited_documents)
        )
        logger.info(
            "Ответ сформирован user_namespace={} sources={}",
            self._stores.namespace_for(user_id),
            len(sources),
        )
        return StudyReply(text=answer, sources=sources)

    def _run_answer_pipeline(self, *, user_id: int, question: str) -> dict:
        """Один раз повторить запрос при временном таймауте Pinecone."""

        pipeline = self._generation_pipeline(user_id)
        pipeline_input = {
            "text_embedder": {"text": question},
            "prompt_builder": {"question": question},
        }
        for attempt in range(2):
            try:
                return pipeline.run(
                    pipeline_input,
                    include_outputs_from={"retriever"},
                )
            except Exception as error:
                if attempt == 0 and _caused_by_pinecone_timeout(error):
                    logger.warning("Pinecone не ответил вовремя. Повторяю поиск один раз.")
                    time.sleep(1)
                    continue
                raise

        raise RuntimeError("Повторный запуск пайплайна не выполнен")

    def document_count(self, user_id: int) -> int:
        """Вернуть число сохранённых чанков текущего пользователя."""

        return self._stores.count(user_id)

    def clear_documents(self, user_id: int) -> None:
        """Очистить базу знаний только текущего пользователя."""

        self._stores.clear(user_id)

    def _ingestion_pipeline(self, user_id: int) -> Pipeline:
        namespace = self._stores.namespace_for(user_id)
        with self._pipelines_lock:
            if namespace not in self._ingestion_pipelines:
                self._ingestion_pipelines[namespace] = build_ingestion_pipeline(
                    self._settings,
                    self._stores.store_for(user_id),
                )
            return self._ingestion_pipelines[namespace]

    def _generation_pipeline(self, user_id: int) -> Pipeline:
        namespace = self._stores.namespace_for(user_id)
        with self._pipelines_lock:
            if namespace not in self._generation_pipelines:
                self._generation_pipelines[namespace] = build_generation_pipeline(
                    self._settings,
                    self._stores.store_for(user_id),
                )
            return self._generation_pipelines[namespace]


def _source_label(document: Document) -> str:
    file_name = str(document.meta.get("file_name", "неизвестный файл"))
    pages = str(document.meta.get("page_numbers", "")).strip()
    return file_name if not pages else f"{file_name}, стр. {pages}"


def _extract_cited_documents(
    raw_answer: str,
    documents: list[Document],
) -> tuple[str, tuple[Document, ...]]:
    """Удалить служебную метку и выбрать только процитированные фрагменты."""

    marker = re.search(r"\[\[SOURCES:\s*([^\]]*)\]\]\s*$", raw_answer, re.IGNORECASE)
    if marker is None:
        logger.warning("Модель не вернула служебную метку источников")
        return raw_answer.strip(), ()

    answer = raw_answer[: marker.start()].strip()
    answer = re.sub(
        r"\s*\[\[S\d+\](?:,\s*\[S\d+\])*\]",
        "",
        answer,
        flags=re.IGNORECASE,
    )
    answer = re.sub(
        r"\s*\[S\d+(?:\s*,\s*S\d+)*\]",
        "",
        answer,
        flags=re.IGNORECASE,
    )
    selected: list[Document] = []
    seen_indexes: set[int] = set()
    for value in re.findall(r"S(\d+)", marker.group(1), re.IGNORECASE):
        index = int(value) - 1
        if 0 <= index < len(documents) and index not in seen_indexes:
            selected.append(documents[index])
            seen_indexes.add(index)
    return answer, tuple(selected)


def _one_sentence(text: str) -> str:
    """Оставить первое законченное предложение для требования домашней работы."""

    compact = re.sub(r"\s+", " ", text).strip()
    match = re.match(r"^(.+?[.!?])(?:\s|$)", compact)
    return match.group(1) if match else compact.rstrip(".!?") + "."


def _caused_by_pinecone_timeout(error: BaseException) -> bool:
    """Найти таймаут Pinecone в цепочке исключений Haystack."""

    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, PineconeTimeoutError):
            return True
        visited.add(id(current))
        current = current.__cause__ or current.__context__
    return False
