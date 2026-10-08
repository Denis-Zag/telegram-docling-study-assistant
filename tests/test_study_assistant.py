"""Проверки прикладной логики без сетевых обращений."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from haystack import Document
from pinecone.errors.exceptions import PineconeTimeoutError

from app.config import Settings
from app.study_assistant import StudyAssistantService, UnsupportedDocumentError


class FakeStores:
    def __init__(self) -> None:
        self.cleared: list[int] = []

    @staticmethod
    def namespace_for(user_id: int) -> str:
        return f"namespace-{user_id}"

    @staticmethod
    def store_for(user_id: int) -> Any:
        return SimpleNamespace(user_id=user_id)

    @staticmethod
    def count(user_id: int) -> int:
        return user_id

    def clear(self, user_id: int) -> None:
        self.cleared.append(user_id)


class FakePipeline:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def run(self, data: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(data)
        return self.result


class TimeoutOncePipeline(FakePipeline):
    def run(self, data: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(data)
        if len(self.calls) == 1:
            try:
                raise PineconeTimeoutError("Временный таймаут")
            except PineconeTimeoutError as error:
                raise RuntimeError("Ошибка компонента retriever") from error
        return self.result


def make_settings() -> Settings:
    return Settings(
        telegram_bot_token="telegram-token-test",
        proxyapi_key="proxyapi-key-test",
        pinecone_api_key="pinecone-key-test",
    )


def test_document_processing_uses_pipeline_and_returns_one_sentence() -> None:
    stores = FakeStores()
    service = StudyAssistantService(make_settings(), stores)  # type: ignore[arg-type]
    pipeline = FakePipeline(
        {
            "writer": {"documents_written": 4},
            "summary_llm": {
                "replies": [SimpleNamespace(text="Главная тема урока. Второе предложение.")]
            },
        }
    )
    service._ingestion_pipelines["namespace-7"] = pipeline  # noqa: SLF001

    result = service.process_document(
        user_id=7,
        file_name="lesson.docx",
        content=b"document-content",
    )

    assert result.chunks_written == 4
    assert result.summary == "Главная тема урока."
    assert pipeline.calls[0]["converter"]["original_name"] == "lesson.docx"


def test_answer_returns_unique_source_labels() -> None:
    stores = FakeStores()
    service = StudyAssistantService(make_settings(), stores)  # type: ignore[arg-type]
    first_document = Document(
        content="Общий контекст",
        meta={"file_name": "lesson.pdf", "page_numbers": "1"},
    )
    cited_document = Document(
        content="Точный ответ",
        meta={"file_name": "lesson.pdf", "page_numbers": "2"},
    )
    pipeline = FakePipeline(
        {
            "retriever": {
                "documents": [first_document, cited_document, cited_document]
            },
            "llm": {
                "replies": [
                    SimpleNamespace(
                        text=(
                            "Pipeline соединяет компоненты [[S1], [S2]].\n"
                            "[[SOURCES: S2,S3]]"
                        )
                    )
                ]
            },
        }
    )
    service._generation_pipelines["namespace-7"] = pipeline  # noqa: SLF001

    reply = service.answer(user_id=7, question="Что такое pipeline?")

    assert reply.text == "Pipeline соединяет компоненты."
    assert reply.sources == ("lesson.pdf, стр. 2",)


def test_answer_retries_pinecone_timeout_once(monkeypatch: pytest.MonkeyPatch) -> None:
    stores = FakeStores()
    service = StudyAssistantService(make_settings(), stores)  # type: ignore[arg-type]
    document = Document(
        content="Ответ",
        meta={"file_name": "lesson.pdf", "page_numbers": "2"},
    )
    pipeline = TimeoutOncePipeline(
        {
            "retriever": {"documents": [document]},
            "llm": {
                "replies": [
                    SimpleNamespace(
                        text="Повторный поиск сработал.\n[[SOURCES: S1]]"
                    )
                ]
            },
        }
    )
    service._generation_pipelines["namespace-7"] = pipeline  # noqa: SLF001
    monkeypatch.setattr("app.study_assistant.time.sleep", lambda _seconds: None)

    reply = service.answer(user_id=7, question="Повтори поиск")

    assert reply.text == "Повторный поиск сработал."
    assert len(pipeline.calls) == 2


def test_unsupported_extension_is_rejected_before_pipeline() -> None:
    service = StudyAssistantService(make_settings(), FakeStores())  # type: ignore[arg-type]

    with pytest.raises(UnsupportedDocumentError, match="PDF и DOCX"):
        service.process_document(user_id=1, file_name="lesson.txt", content=b"text")
