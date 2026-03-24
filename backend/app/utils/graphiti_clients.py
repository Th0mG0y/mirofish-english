from __future__ import annotations

import logging
from math import exp, sqrt

import openai
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.helpers import semaphore_gather
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient as GraphitiOpenAIClient
from openai import AsyncOpenAI

from ..config import Config

logger = logging.getLogger(__name__)


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


class CompatibleOpenAIRerankerClient(CrossEncoderClient):
    def __init__(self, config: LLMConfig | None = None, client: AsyncOpenAI | None = None):
        self.config = config or LLMConfig()
        self.client = client or AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []

        try:
            scores = await semaphore_gather(
                *[self._score_passage(query, passage) for passage in passages]
            )
        except openai.RateLimitError as exc:
            raise exc
        except Exception as exc:
            logger.error(f'Error in generating reranker response: {exc}')
            raise

        results = [(passage, score) for passage, score in zip(passages, scores, strict=True)]
        results.sort(reverse=True, key=lambda item: item[1])
        return results

    async def _score_passage(self, query: str, passage: str) -> float:
        response = await self._create_relevance_response(query, passage)
        choice = response.choices[0]
        logprobs = getattr(choice, 'logprobs', None)

        if logprobs is not None and getattr(logprobs, 'content', None):
            top_logprobs = logprobs.content[0].top_logprobs or []
            if top_logprobs:
                top_logprob = top_logprobs[0]
                probability = exp(top_logprob.logprob)
                token = top_logprob.token.strip().split(' ')[0].lower()
                return probability if token == 'true' else 1.0 - probability

        content = (getattr(getattr(choice, 'message', None), 'content', '') or '').strip().lower()
        return 1.0 if content.startswith('true') else 0.0

    async def _create_relevance_response(self, query: str, passage: str):
        request_kwargs = {
            'model': self.config.model or Config.LLM_MODEL_NAME,
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are an expert tasked with determining whether the passage is relevant to the query',
                },
                {
                    'role': 'user',
                    'content': f"""
                           Respond with "True" if PASSAGE is relevant to QUERY and "False" otherwise.
                           <PASSAGE>
                           {passage}
                           </PASSAGE>
                           <QUERY>
                           {query}
                           </QUERY>
                           """,
                },
            ],
            'temperature': 0,
        }
        full_scoring_kwargs = {
            'logit_bias': {'6432': 1, '7983': 1},
            'logprobs': True,
            'top_logprobs': 2,
        }

        for extra_kwargs in self._get_request_attempts(full_scoring_kwargs):
            try:
                return await self.client.chat.completions.create(
                    **request_kwargs,
                    **extra_kwargs,
                )
            except Exception as exc:
                if not self._is_retryable_openai_compatibility_error(exc):
                    raise

        raise RuntimeError('Unable to create a reranker response with the configured OpenAI-compatible model')

    def _get_token_limit_kwargs(self) -> dict[str, int]:
        model_name = (self.config.model or '').lower()
        if model_name.startswith('gpt-5'):
            return {'max_completion_tokens': 8}
        return {'max_tokens': 8}

    def _get_alternate_token_limit_kwargs(self, token_limit_kwargs: dict[str, int]) -> dict[str, int]:
        if 'max_tokens' in token_limit_kwargs:
            return {'max_completion_tokens': 8}
        return {'max_tokens': 8}

    def _get_request_attempts(self, full_scoring_kwargs: dict[str, object]) -> list[dict[str, object]]:
        token_limit_kwargs = self._get_token_limit_kwargs()
        alternate_token_limit_kwargs = self._get_alternate_token_limit_kwargs(token_limit_kwargs)

        attempts = [
            {**token_limit_kwargs, **full_scoring_kwargs},
            token_limit_kwargs,
            {**alternate_token_limit_kwargs, **full_scoring_kwargs},
            alternate_token_limit_kwargs,
        ]

        deduplicated_attempts: list[dict[str, object]] = []
        seen_signatures: set[tuple[tuple[str, object], ...]] = set()
        for attempt in attempts:
            signature = tuple(sorted((key, repr(value)) for key, value in attempt.items()))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            deduplicated_attempts.append(attempt)

        return deduplicated_attempts

    def _is_retryable_openai_compatibility_error(self, exc: Exception) -> bool:
        error_message = str(exc)
        return (
            "Unsupported parameter: 'max_tokens'" in error_message
            or "Use 'max_completion_tokens' instead" in error_message
            or "Unsupported parameter: 'max_completion_tokens'" in error_message
            or "Use 'max_tokens' instead" in error_message
            or "Unsupported parameter: 'logit_bias'" in error_message
            or "Unsupported parameter: 'logprobs'" in error_message
            or "Unsupported parameter: 'top_logprobs'" in error_message
            or 'Could not finish the message because max_tokens or model output limit was reached' in error_message
        )


def create_graphiti_llm_client():
    if Config.GRAPHITI_LLM_PROVIDER == 'anthropic':
        from graphiti_core.llm_client.anthropic_client import AnthropicClient as GraphitiAnthropicClient
        return GraphitiAnthropicClient(
            config=LLMConfig(
                api_key=Config.get_graphiti_llm_api_key(),
                model=Config.get_graphiti_llm_model(),
            )
        )

    base_url = Config.GRAPHITI_LLM_BASE_URL or Config.LLM_BASE_URL
    if not base_url and Config.GRAPHITI_LLM_PROVIDER == 'ollama':
        base_url = Config.OLLAMA_BASE_URL

    return GraphitiOpenAIClient(
        config=LLMConfig(
            api_key=Config.get_graphiti_llm_api_key(),
            base_url=base_url,
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
        return CompatibleOpenAIRerankerClient(
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
