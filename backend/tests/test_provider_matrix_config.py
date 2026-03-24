from app.config import Config


def apply_config(monkeypatch, **overrides):
    for key, value in overrides.items():
        monkeypatch.setattr(Config, key, value)


def base_overrides():
    return {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
        "ANTHROPIC_MODEL_NAME": "claude-sonnet-4-6",
        "LLM_MODEL_NAME": "gpt-5.4-mini",
        "LLM_BASE_URL": "https://api.openai.com/v1",
        "SEARCH_MODEL": "",
        "GRAPHITI_LLM_API_KEY": "",
        "GRAPHITI_LLM_BASE_URL": "",
        "GRAPHITI_LLM_MODEL": "",
        "GRAPHITI_EMBEDDER_API_KEY": "",
        "GRAPHITI_EMBEDDER_BASE_URL": "",
        "GRAPHITI_EMBEDDER_MODEL": "text-embedding-3-small",
        "GRAPHITI_RERANKER_API_KEY": "",
        "GRAPHITI_RERANKER_BASE_URL": "",
        "GRAPHITI_RERANKER_MODEL": "gpt-5.4-mini",
    }


def test_openai_only_matrix_validates(monkeypatch):
    apply_config(
        monkeypatch,
        **base_overrides(),
        LLM_PROVIDER="openai",
        LLM_API_KEY="openai-key",
        ANTHROPIC_API_KEY="",
        SEARCH_PROVIDER="openai",
        GRAPHITI_LLM_PROVIDER="openai",
        GRAPHITI_EMBEDDER_PROVIDER="openai",
        GRAPHITI_RERANKER_PROVIDER="openai",
    )

    assert Config.validate() == []


def test_anthropic_plus_ollama_matrix_validates(monkeypatch):
    overrides = {
        **base_overrides(),
        "LLM_PROVIDER": "anthropic",
        "LLM_API_KEY": "",
        "ANTHROPIC_API_KEY": "anthropic-key",
        "SEARCH_PROVIDER": "anthropic",
        "GRAPHITI_LLM_PROVIDER": "anthropic",
        "GRAPHITI_EMBEDDER_PROVIDER": "ollama",
        "GRAPHITI_EMBEDDER_BASE_URL": "http://localhost:11434/v1",
        "GRAPHITI_EMBEDDER_MODEL": "nomic-embed-text",
        "GRAPHITI_RERANKER_PROVIDER": "ollama",
        "GRAPHITI_RERANKER_BASE_URL": "http://localhost:11434/v1",
        "GRAPHITI_RERANKER_MODEL": "nomic-embed-text",
    }
    apply_config(monkeypatch, **overrides)

    assert Config.validate() == []


def test_mixed_provider_matrix_validates(monkeypatch):
    overrides = {
        **base_overrides(),
        "LLM_PROVIDER": "anthropic",
        "LLM_API_KEY": "openai-key",
        "ANTHROPIC_API_KEY": "anthropic-key",
        "SEARCH_PROVIDER": "openai",
        "GRAPHITI_LLM_PROVIDER": "openai",
        "GRAPHITI_LLM_MODEL": "gpt-5.4-mini",
        "GRAPHITI_EMBEDDER_PROVIDER": "ollama",
        "GRAPHITI_EMBEDDER_BASE_URL": "http://localhost:11434/v1",
        "GRAPHITI_EMBEDDER_MODEL": "nomic-embed-text",
        "GRAPHITI_RERANKER_PROVIDER": "lmstudio",
        "GRAPHITI_RERANKER_BASE_URL": "http://localhost:1234/v1",
        "GRAPHITI_RERANKER_MODEL": "text-embedding-nomic-embed-text-v1.5",
    }
    apply_config(monkeypatch, **overrides)

    assert Config.validate() == []
