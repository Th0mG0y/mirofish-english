import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("graphiti_core")

from graphiti_core.llm_client.config import LLMConfig

from app.utils.graphiti_clients import (
    CompatibleOpenAIRerankerClient,
    EmbeddingSimilarityRerankerClient,
)


class FakeEmbedder:
    async def create(self, input_data):
        if input_data == "apple":
            return [1.0, 0.0]
        return [0.0, 1.0]

    async def create_batch(self, input_data_list):
        vectors = {
            "apple pie": [1.0, 0.0],
            "banana bread": [0.0, 1.0],
            "fruit salad": [0.6, 0.4],
        }
        return [vectors[item] for item in input_data_list]


def test_embedding_similarity_reranker_orders_passages_by_similarity():
    reranker = EmbeddingSimilarityRerankerClient(FakeEmbedder())
    result = asyncio.run(
        reranker.rank(
            "apple",
            ["banana bread", "fruit salad", "apple pie"],
        )
    )

    assert [passage for passage, _ in result] == [
        "apple pie",
        "fruit salad",
        "banana bread",
    ]


class FakeRetryingCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if "max_tokens" in kwargs:
            raise RuntimeError(
                "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead."
            )

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="True"),
                    logprobs=None,
                )
            ]
        )


def test_compatible_openai_reranker_retries_with_max_completion_tokens():
    fake_completions = FakeRetryingCompletions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))
    reranker = CompatibleOpenAIRerankerClient(
        config=LLMConfig(model="gpt-4.1-nano"),
        client=fake_client,
    )

    result = asyncio.run(reranker.rank("query", ["passage"]))

    assert result == [("passage", 1.0)]
    assert "max_tokens" in fake_completions.calls[0]
    assert "logit_bias" not in fake_completions.calls[1]
    assert "max_tokens" in fake_completions.calls[1]
    assert "max_completion_tokens" in fake_completions.calls[2]


class FakeGpt5Completions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="True"),
                    logprobs=None,
                )
            ]
        )


def test_compatible_openai_reranker_prefers_max_completion_tokens_for_gpt5():
    fake_completions = FakeGpt5Completions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))
    reranker = CompatibleOpenAIRerankerClient(
        config=LLMConfig(model="gpt-5.4-mini"),
        client=fake_client,
    )

    result = asyncio.run(reranker.rank("query", ["passage"]))

    assert result == [("passage", 1.0)]
    assert len(fake_completions.calls) == 1
    assert "max_completion_tokens" in fake_completions.calls[0]


class FakeUnsupportedLogitBiasCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if "logit_bias" in kwargs:
            raise RuntimeError(
                "Unsupported parameter: 'logit_bias' is not supported with this model."
            )

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="True"),
                    logprobs=None,
                )
            ]
        )


def test_compatible_openai_reranker_falls_back_when_logit_bias_is_unsupported():
    fake_completions = FakeUnsupportedLogitBiasCompletions()
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=fake_completions))
    reranker = CompatibleOpenAIRerankerClient(
        config=LLMConfig(model="gpt-5.4-mini"),
        client=fake_client,
    )

    result = asyncio.run(reranker.rank("query", ["passage"]))

    assert result == [("passage", 1.0)]
    assert "logit_bias" in fake_completions.calls[0]
    assert "logit_bias" not in fake_completions.calls[1]
