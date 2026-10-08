"""Проверки ограничений промптов учебного ассистента."""

from __future__ import annotations

from haystack import Document

from app.components.prompts import StudyAnswerPromptBuilder, SummaryPromptBuilder


def test_summary_prompt_requires_exactly_one_grounded_sentence() -> None:
    message = SummaryPromptBuilder().run("Текст урока", "lesson.docx")["messages"][0]

    assert "ровно одно короткое предложение" in message.text
    assert "Не добавляй факты" in message.text
    assert "lesson.docx" in message.text


def test_answer_prompt_contains_sources_and_no_hallucination_rule() -> None:
    document = Document(
        content="Haystack соединяет компоненты в pipeline.",
        meta={"file_name": "lesson.pdf", "page_numbers": "2"},
    )

    message = StudyAnswerPromptBuilder().run([document], "Что такое pipeline?")["messages"][0]

    assert "lesson.pdf, стр. 2" in message.text
    assert "[S1]" in message.text
    assert "[[SOURCES: S2,S5]]" in message.text
    assert "Используй только" in message.text
    assert "нет достаточной информации" in message.text
