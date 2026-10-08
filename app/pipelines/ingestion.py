"""Пайплайн загрузки документа в Pinecone и создания резюме."""

from __future__ import annotations

from haystack import Pipeline
from haystack.components.embedders import OpenAIDocumentEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.components.writers import DocumentWriter
from haystack.document_stores.types import DuplicatePolicy
from haystack.utils import Secret
from haystack_integrations.document_stores.pinecone import PineconeDocumentStore

from app.components.docling_converter import DoclingDocumentConverter
from app.components.prompts import SummaryPromptBuilder
from app.config import Settings


def build_ingestion_pipeline(
    settings: Settings,
    document_store: PineconeDocumentStore,
) -> Pipeline:
    """Соединить Docling, embedding, запись в Pinecone и краткое резюме."""

    secret = Secret.from_token(settings.proxyapi_key)
    pipeline = Pipeline()
    pipeline.add_component("converter", DoclingDocumentConverter())
    pipeline.add_component(
        "document_embedder",
        OpenAIDocumentEmbedder(
            api_key=secret,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimension,
            api_base_url=settings.proxyapi_base_url,
            timeout=settings.http_timeout_seconds,
            max_retries=2,
            progress_bar=False,
            raise_on_failure=True,
        ),
    )
    pipeline.add_component(
        "writer",
        DocumentWriter(
            document_store=document_store,
            policy=DuplicatePolicy.OVERWRITE,
        ),
    )
    pipeline.add_component("summary_prompt", SummaryPromptBuilder())
    pipeline.add_component(
        "summary_llm",
        OpenAIChatGenerator(
            api_key=secret,
            model=settings.chat_model,
            api_base_url=settings.proxyapi_base_url,
            timeout=settings.http_timeout_seconds,
            max_retries=2,
            generation_kwargs={"temperature": 0},
        ),
    )

    pipeline.connect("converter.documents", "document_embedder.documents")
    pipeline.connect("document_embedder.documents", "writer.documents")
    pipeline.connect("converter.summary_text", "summary_prompt.text")
    pipeline.connect("summary_prompt.messages", "summary_llm.messages")
    return pipeline
