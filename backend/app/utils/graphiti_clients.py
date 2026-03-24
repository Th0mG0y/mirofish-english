from __future__ import annotations

from math import sqrt

from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.anthropic_client import AnthropicClient as GraphitiAnthropicClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient as GraphitiOpenAIClient

from ..config import Config


class EmbeddingSimilarityRerankerClient(CrossEncoderClient):
    def __init__(self, embedder: EmbedderClient):
        self.embedder = embedder

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []

        query_embedding = await self.embedder.create(query)
        passage_embeddings = await self.embedder.create_batch(passages)

        results = [
            (passage, self._cosine_similarity(query_embedding, embedding))
            for passage, embedding in zip(passages, passage_embeddings, strict=True)
        ]
        results.sort(key=lambda item: item[1], reverse=True)
        return results

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        size = min(len(left), len(right))
        if size == 0:
            return 0.0

        dot_product = sum(left[idx] * right[idx] for idx in range(size))
        left_norm = sqrt(sum(left[idx] * left[idx] for idx in range(size)))
        right_norm = sqrt(sum(right[idx] * right[idx] for idx in range(size)))

        if left_norm == 0 or right_norm == 0:
            return 0.0

        return dot_product / (left_norm * right_norm)


def create_graphiti_llm_client():
    if Config.GRAPHITI_LLM_PROVIDER == 'anthropic':
        return GraphitiAnthropicClient(
            config=LLMConfig(
                api_key=Config.get_graphiti_llm_api_key(),
                model=Config.get_graphiti_llm_model(),
            )
        )

    return GraphitiOpenAIClient(
        config=LLMConfig(
            api_key=Config.get_graphiti_llm_api_key(),
            base_url=Config.GRAPHITI_LLM_BASE_URL or Config.LLM_BASE_URL,
            model=Config.get_graphiti_llm_model(),
        )
    )


def create_graphiti_embedder(
    provider_name: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> EmbedderClient:
    resolved_provider = (provider_name or Config.GRAPHITI_EMBEDDER_PROVIDER).lower()
    resolved_base_url = Config.get_graphiti_openai_compatible_base_url(
        resolved_provider,
        base_url or Config.GRAPHITI_EMBEDDER_BASE_URL or None,
    )
    resolved_api_key = Config.get_graphiti_openai_compatible_api_key(
        resolved_provider,
        explicit_api_key=api_key or Config.GRAPHITI_EMBEDDER_API_KEY or None,
        explicit_base_url=resolved_base_url,
    )

    return OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            embedding_model=model or Config.GRAPHITI_EMBEDDER_MODEL,
        )
    )


def create_graphiti_reranker(embedder: EmbedderClient | None = None) -> CrossEncoderClient:
    resolved_provider = Config.GRAPHITI_RERANKER_PROVIDER

    if resolved_provider == 'openai':
        resolved_base_url = Config.get_graphiti_openai_compatible_base_url(
            resolved_provider,
            Config.GRAPHITI_RERANKER_BASE_URL or None,
        )
        resolved_api_key = Config.get_graphiti_openai_compatible_api_key(
            resolved_provider,
            explicit_api_key=Config.GRAPHITI_RERANKER_API_KEY or None,
            explicit_base_url=resolved_base_url,
        )
        return OpenAIRerankerClient(
            config=LLMConfig(
                api_key=resolved_api_key,
                base_url=resolved_base_url,
                model=Config.GRAPHITI_RERANKER_MODEL,
            )
        )

    can_reuse_embedder = (
        embedder is not None
        and resolved_provider == Config.GRAPHITI_EMBEDDER_PROVIDER
        and Config.GRAPHITI_RERANKER_MODEL == Config.GRAPHITI_EMBEDDER_MODEL
        and (Config.GRAPHITI_RERANKER_BASE_URL or '') == (Config.GRAPHITI_EMBEDDER_BASE_URL or '')
        and (Config.GRAPHITI_RERANKER_API_KEY or '') == (Config.GRAPHITI_EMBEDDER_API_KEY or '')
    )

    similarity_embedder = embedder if can_reuse_embedder else create_graphiti_embedder(
        provider_name=resolved_provider,
        model=Config.GRAPHITI_RERANKER_MODEL,
        api_key=Config.GRAPHITI_RERANKER_API_KEY or None,
        base_url=Config.GRAPHITI_RERANKER_BASE_URL or None,
    )
    return EmbeddingSimilarityRerankerClient(similarity_embedder)
