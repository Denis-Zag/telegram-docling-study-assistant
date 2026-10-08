"""Обработчики Telegram для учебного ассистента по документам."""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from telebot import TeleBot, types

from app.study_assistant import StudyAssistantService, UnsupportedDocumentError

START_TEXT = """
Привет! Я учебный ассистент по вашим документам.

Отправьте мне PDF или DOCX. Я обработаю файл через Docling, сохраню его
фрагменты в Pinecone и пришлю краткое резюме. После этого задавайте вопросы
по загруженным материалам обычными текстовыми сообщениями.

Команды: /help, /document_status, /clear.
""".strip()

HELP_TEXT = """
Как работать с ботом:
1. Отправьте PDF или DOCX как документ.
2. Дождитесь сообщения об успешной обработке.
3. Задайте вопрос по содержимому файла.

/document_status — число сохранённых фрагментов.
/clear — удалить только ваши загруженные материалы.
""".strip()


def create_bot(token: str, assistant: StudyAssistantService) -> TeleBot:
    """Создать Telegram-бота и зарегистрировать обработчики."""

    bot = TeleBot(token, parse_mode=None)

    @bot.message_handler(commands=["start"])
    def start_handler(message: types.Message) -> None:
        bot.send_message(message.chat.id, START_TEXT)

    @bot.message_handler(commands=["help"])
    def help_handler(message: types.Message) -> None:
        bot.send_message(message.chat.id, HELP_TEXT)

    @bot.message_handler(commands=["document_status"])
    def document_status_handler(message: types.Message) -> None:
        try:
            count = assistant.document_count(message.from_user.id)
            bot.send_message(message.chat.id, f"В вашей базе знаний фрагментов: {count}.")
        except Exception:
            logger.exception("Ошибка команды /document_status")
            bot.send_message(message.chat.id, "Не удалось проверить базу знаний.")

    @bot.message_handler(commands=["clear"])
    def clear_handler(message: types.Message) -> None:
        try:
            assistant.clear_documents(message.from_user.id)
            bot.send_message(message.chat.id, "Ваши учебные материалы удалены.")
        except Exception:
            logger.exception("Ошибка команды /clear")
            bot.send_message(message.chat.id, "Не удалось очистить базу знаний.")

    @bot.message_handler(content_types=["document"])
    def document_handler(message: types.Message) -> None:
        file_name = Path(message.document.file_name or "document").name
        try:
            bot.send_message(
                message.chat.id,
                "Файл получен. Запускаю анализ и сохранение. Это может занять некоторое время…",
            )
            telegram_file = bot.get_file(message.document.file_id)
            content = bot.download_file(telegram_file.file_path)
            result = assistant.process_document(
                user_id=message.from_user.id,
                file_name=file_name,
                content=content,
            )
            bot.send_message(
                message.chat.id,
                "Готово. Я изучил этот файл, теперь можем его обсудить.\n\n"
                f"Краткое резюме: {result.summary}",
            )
        except UnsupportedDocumentError as error:
            bot.send_message(message.chat.id, str(error))
        except Exception:
            logger.exception("Ошибка обработки документа file_name={}", file_name)
            bot.send_message(
                message.chat.id,
                "Не удалось обработать файл. Проверьте формат и попробуйте ещё раз.",
            )

    @bot.message_handler(
        content_types=["text"],
        func=lambda message: not message.text.startswith("/"),
    )
    def text_handler(message: types.Message) -> None:
        try:
            reply = assistant.answer(user_id=message.from_user.id, question=message.text)
            text = reply.text
            if reply.sources:
                text += "\n\nИсточники:\n" + "\n".join(f"• {item}" for item in reply.sources)
            bot.send_message(message.chat.id, text[:4096])
        except Exception:
            logger.exception("Непредвиденная ошибка обработки Telegram-сообщения")
            bot.send_message(
                message.chat.id,
                "Не удалось обработать вопрос. Попробуйте ещё раз немного позже.",
            )

    @bot.message_handler(func=lambda _message: True)
    def fallback_handler(message: types.Message) -> None:
        bot.send_message(message.chat.id, "Отправьте PDF, DOCX или текстовый вопрос.")

    return bot
