"""Внутренние модели данных учебного ассистента."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentProcessingResult:
    """Результат обработки и сохранения одного документа."""

    file_name: str
    chunks_written: int
    summary: str


@dataclass(frozen=True, slots=True)
class StudyReply:
    """Ответ по учебным материалам и использованные источники."""

    text: str
    sources: tuple[str, ...] = ()
