import asyncio

import pytest

pytest.importorskip("graphiti_core")

from app.utils.graphiti_clients import EmbeddingSimilarityRerankerClient


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
