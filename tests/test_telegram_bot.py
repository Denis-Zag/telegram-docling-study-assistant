"""Проверки Telegram-обработчиков без запуска polling."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.models import DocumentProcessingResult, StudyReply
from app.telegram_bot import create_bot


class FakeAssistant:
    def __init__(self) -> None:
        self.document_request: dict[str, Any] | None = None
        self.question_request: dict[str, Any] | None = None

    def process_document(self, **kwargs: Any) -> DocumentProcessingResult:
        self.document_request = kwargs
        return DocumentProcessingResult("lesson.pdf", 3, "Урок объясняет пайплайны.")

    def answer(self, **kwargs: Any) -> StudyReply:
        self.question_request = kwargs
        return StudyReply("Это последовательность компонентов.", ("lesson.pdf, стр. 2",))

    def document_count(self, user_id: int) -> int:
        return 3

    def clear_documents(self, user_id: int) -> None:
        return None


def handler(bot: Any, name: str) -> Any:
    return next(
        item["function"]
        for item in bot.message_handlers
        if item["function"].__name__ == name
    )


def test_document_handler_downloads_and_processes_file(monkeypatch: Any) -> None:
    assistant = FakeAssistant()
    bot = create_bot("1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZABCDE", assistant)  # type: ignore[arg-type]
    sent: list[str] = []
    monkeypatch.setattr(bot, "send_message", lambda _chat_id, text: sent.append(text))
    monkeypatch.setattr(bot, "get_file", lambda _file_id: SimpleNamespace(file_path="remote.pdf"))
    monkeypatch.setattr(bot, "download_file", lambda _path: b"pdf-content")
    message = SimpleNamespace(
        chat=SimpleNamespace(id=55),
        from_user=SimpleNamespace(id=77),
        document=SimpleNamespace(file_name="lesson.pdf", file_id="file-1"),
    )

    handler(bot, "document_handler")(message)

    assert assistant.document_request == {
        "user_id": 77,
        "file_name": "lesson.pdf",
        "content": b"pdf-content",
    }
    assert "Краткое резюме: Урок объясняет пайплайны." in sent[-1]


def test_text_handler_appends_sources(monkeypatch: Any) -> None:
    assistant = FakeAssistant()
    bot = create_bot("1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZABCDE", assistant)  # type: ignore[arg-type]
    sent: list[str] = []
    monkeypatch.setattr(bot, "send_message", lambda _chat_id, text: sent.append(text))
    message = SimpleNamespace(
        chat=SimpleNamespace(id=55),
        from_user=SimpleNamespace(id=77),
        text="Что такое pipeline?",
    )

    handler(bot, "text_handler")(message)

    assert assistant.question_request == {"user_id": 77, "question": "Что такое pipeline?"}
    assert "Источники:" in sent[0]
    assert "lesson.pdf, стр. 2" in sent[0]
