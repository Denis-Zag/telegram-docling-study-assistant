"""Живая проверка Docling, ProxyAPI, Pinecone и Telegram без запуска polling."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "false")

from telebot import TeleBot

from app.config import Settings
from app.logging_config import configure_logging
from app.services import build_assistant


def parse_args() -> argparse.Namespace:
    """Прочитать параметры безопасной живой проверки."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path, help="Локальный PDF или DOCX для проверки")
    parser.add_argument("--env-file", default=".env", help="Путь к локальному env-файлу")
    parser.add_argument(
        "--question",
        default="Кратко сформулируй главную тему документа.",
        help="Контрольный вопрос по загруженному документу",
    )
    return parser.parse_args()


def main() -> None:
    """Выполнить полный сценарий и гарантированно очистить тестовый namespace."""

    args = parse_args()
    document_path = args.document.resolve()
    if not document_path.is_file():
        raise FileNotFoundError(f"Документ не найден: {document_path}")

    settings = Settings(_env_file=Path(args.env_file).resolve())  # type: ignore[call-arg]
    configure_logging(settings.log_level)

    telegram_user = TeleBot(settings.telegram_bot_token).get_me()
    print(f"Telegram: OK (@{telegram_user.username})")

    assistant = build_assistant(settings)
    preflight_user_id = -9_070_001
    assistant.clear_documents(preflight_user_id)
    try:
        processed = assistant.process_document(
            user_id=preflight_user_id,
            file_name=document_path.name,
            content=document_path.read_bytes(),
        )
        if processed.chunks_written < 1:
            raise RuntimeError("Docling не создал чанки для Pinecone")
        print(
            "Docling + ProxyAPI embeddings + Pinecone: OK "
            f"({processed.chunks_written} чанков)"
        )
        print(f"ProxyAPI summary: OK ({processed.summary})")

        reply = assistant.answer(user_id=preflight_user_id, question=args.question)
        if not reply.sources:
            raise RuntimeError("RAG-ответ не содержит источника")
        print(f"Haystack generation pipeline: OK ({reply.text[:160]})")
        print(f"Источник: {', '.join(reply.sources)}")
    finally:
        assistant.clear_documents(preflight_user_id)
        print("Pinecone: тестовый namespace очищен")

    print("Preflight завершён. Telegram polling не запускался.")


if __name__ == "__main__":
    main()
