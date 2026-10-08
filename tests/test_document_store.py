"""Проверки изоляции пользовательских пространств Pinecone."""

from __future__ import annotations

from app.document_store import PineconeStoreRegistry


def test_namespaces_are_stable_hidden_and_isolated() -> None:
    first = PineconeStoreRegistry.namespace_for(10)

    assert first == PineconeStoreRegistry.namespace_for(10)
    assert first != PineconeStoreRegistry.namespace_for(11)
    assert "10" not in first
