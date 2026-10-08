"""Сборка зависимостей приложения в одном месте."""

from __future__ import annotations

from app.config import Settings
from app.document_store import PineconeStoreRegistry
from app.study_assistant import StudyAssistantService


def build_assistant(settings: Settings) -> StudyAssistantService:
    """Создать учебного ассистента с изолированными хранилищами Pinecone."""

    stores = PineconeStoreRegistry(settings)
    return StudyAssistantService(settings=settings, stores=stores)
