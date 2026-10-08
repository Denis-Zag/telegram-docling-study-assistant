"""Изолированные пространства документов пользователей в Pinecone."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from threading import Lock

from haystack.utils import Secret
from haystack_integrations.document_stores.pinecone import PineconeDocumentStore

from app.config import Settings


class PineconeStoreRegistry:
    """Создавать и кешировать Pinecone Document Store для каждого пользователя."""

    def __init__(
        self,
        settings: Settings,
        *,
        store_factory: Callable[[str], PineconeDocumentStore] | None = None,
    ) -> None:
        self._settings = settings
        self._store_factory = store_factory or self._create_store
        self._stores: dict[str, PineconeDocumentStore] = {}
        self._lock = Lock()

    @staticmethod
    def namespace_for(user_id: int | str) -> str:
        """Скрыть Telegram ID в названии пространства Pinecone."""

        digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:24]
        return f"study-{digest}"

    def store_for(self, user_id: int) -> PineconeDocumentStore:
        """Вернуть отдельное хранилище документов текущего пользователя."""

        namespace = self.namespace_for(user_id)
        with self._lock:
            if namespace not in self._stores:
                self._stores[namespace] = self._store_factory(namespace)
            return self._stores[namespace]

    def count(self, user_id: int) -> int:
        """Вернуть число сохранённых чанков пользователя."""

        return self.store_for(user_id).count_documents()

    def clear(self, user_id: int) -> None:
        """Удалить только документы текущего пользователя."""

        self.store_for(user_id).delete_all_documents()

    def _create_store(self, namespace: str) -> PineconeDocumentStore:
        return PineconeDocumentStore(
            api_key=Secret.from_token(self._settings.pinecone_api_key),
            index=self._settings.pinecone_index,
            namespace=namespace,
            dimension=self._settings.embedding_dimension,
            metric="cosine",
            spec={
                "serverless": {
                    "cloud": self._settings.pinecone_cloud,
                    "region": self._settings.pinecone_region,
                }
            },
            show_progress=False,
        )
