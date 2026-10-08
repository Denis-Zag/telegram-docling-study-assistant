"""RAG-пайплайн ответа по документам пользователя."""

from __future__ import annotations

from haystack import Pipeline
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.utils import Secret
from haystack_integrations.components.retrievers.pinecone import PineconeEmbeddingRetriever
from haystack_integrations.document_stores.pinecone import PineconeDocumentStore

from app.components.prompts import StudyAnswerPromptBuilder
from app.config import Settings


def build_generation_pipeline(
    settings: Settings,
    document_store: PineconeDocumentStore,
) -> Pipeline:
    """Соединить embedding вопроса, retriever, промпт и языковую модель."""

    secret = Secret.from_token(settings.proxyapi_key)
    pipeline = Pipeline()
    pipeline.add_component(
        "text_embedder",
        OpenAITextEmbedder(
            api_key=secret,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimension,
            api_base_url=settings.proxyapi_base_url,
            timeout=settings.http_timeout_seconds,
            max_retries=2,
        ),
    )
    pipeline.add_component(
        "retriever",
        PineconeEmbeddingRetriever(
            document_store=document_store,
            top_k=settings.document_top_k,
            filters={"field": "meta.type", "operator": "==", "value": "study_document"},
        ),
    )
    pipeline.add_component("prompt_builder", StudyAnswerPromptBuilder())
    pipeline.add_component(
        "llm",
        OpenAIChatGenerator(
            api_key=secret,
            model=settings.chat_model,
            api_base_url=settings.proxyapi_base_url,
            timeout=settings.http_timeout_seconds,
            max_retries=2,
            generation_kwargs={"temperature": 0.1},
        ),
    )

    pipeline.connect("text_embedder.embedding", "retriever.query_embedding")
    pipeline.connect("retriever.documents", "prompt_builder.documents")
    pipeline.connect("prompt_builder.messages", "llm.messages")
    return pipeline
