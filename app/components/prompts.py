"""Компоненты подготовки сообщений для генерации резюме и RAG-ответа."""

from __future__ import annotations

from haystack import Document, component
from haystack.dataclasses import ChatMessage


@component
class SummaryPromptBuilder:
    """Подготовить запрос на резюме документа в одном предложении."""

    @component.output_types(messages=list[ChatMessage])
    def run(self, text: str, file_name: str) -> dict[str, list[ChatMessage]]:
        """Сформировать сообщения для модели без добавления новых фактов."""

        prompt = (
            f"Документ: {file_name}\n\n"
            "Сформулируй по-русски ровно одно короткое предложение, которое передаёт "
            "главную тему документа. Не добавляй факты, которых нет в тексте.\n\n"
            f"Текст документа:\n{text}"
        )
        return {"messages": [ChatMessage.from_user(prompt)]}


@component
class StudyAnswerPromptBuilder:
    """Собрать найденные фрагменты и вопрос в проверяемый RAG-запрос."""

    @component.output_types(messages=list[ChatMessage])
    def run(
        self,
        documents: list[Document],
        question: str,
    ) -> dict[str, list[ChatMessage]]:
        """Потребовать ответ только по переданным учебным материалам."""

        context_parts: list[str] = []
        for index, document in enumerate(documents, start=1):
            file_name = str(document.meta.get("file_name", "неизвестный файл"))
            pages = str(document.meta.get("page_numbers", "")).strip()
            source = file_name if not pages else f"{file_name}, стр. {pages}"
            context_parts.append(
                f"[S{index}] [Источник: {source}]\n{document.content or ''}"
            )

        context = "\n\n".join(context_parts) or "Подходящих фрагментов не найдено."
        prompt = (
            "Ты учебный ассистент. Ответь по-русски, понятно и по делу. "
            "Используй только приведённые фрагменты документов. Если в них нет ответа, "
            "прямо скажи: «В загруженных материалах нет достаточной информации». "
            "Не придумывай сведения. Выбери минимальный набор фрагментов, которые "
            "непосредственно подтверждают ответ. После ответа добавь отдельной последней "
            "строкой служебную метку вида [[SOURCES: S2,S5]]. Не перечисляй в ней "
            "фрагменты только потому, что они были переданы в контексте. Если ответа нет, "
            "используй пустую метку [[SOURCES:]]. Приложение удалит эту строку и покажет "
            "источники отдельно. Не вставляй метки S1, S2 и другие ссылки внутрь текста "
            "ответа.\n\n"
            f"Фрагменты документов:\n{context}\n\n"
            f"Вопрос пользователя:\n{question}"
        )
        return {"messages": [ChatMessage.from_user(prompt)]}
