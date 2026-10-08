"""Telegram-ассистент по учебным документам на Haystack и Docling."""

from __future__ import annotations

import os
from pathlib import Path

# Учебный проект не отправляет анонимную телеметрию Haystack.
os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "false")

# Модели Docling могут занимать заметное место. Кеш храним внутри проекта на
# диске D, а не в почти заполненном пользовательском каталоге диска C.
project_cache = Path(__file__).resolve().parents[1] / ".cache"
os.environ.setdefault("DOCLING_CACHE_DIR", str(project_cache / "docling"))
os.environ.setdefault("HF_HOME", str(project_cache / "huggingface"))
