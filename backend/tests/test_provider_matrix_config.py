import asyncio
from types import SimpleNamespace

from graphiti_core.prompts.models import Message
from graphiti_core.prompts.dedupe_edges import EdgeDuplicate
from pydantic import create_model

from app.config import Config
from app.utils.graphiti_clients import create_graphiti_llm_client
from app.utils.llm_provider import AnthropicProvider, ClaudeCliProvider


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


def test_claude_cli_api_key_uses_explicit_configured_path(monkeypatch, tmp_path):
    credentials_dir = tmp_path / ".claude"
    credentials_dir.mkdir(parents=True, exist_ok=True)
    credentials_file = credentials_dir / ".credentials.json"
    credentials_file.write_text('{"api_key": "configured-claude-key"}', encoding="utf-8")

    apply_config(
        monkeypatch,
        CLAUDE_CLI_USE_CREDENTIALS=True,
        CLAUDE_CLI_CREDENTIALS_FILE=str(credentials_file),
    )

    assert Config.get_claude_cli_api_key() == "configured-claude-key"


def test_claude_cli_api_key_does_not_fallback_to_other_paths(monkeypatch, tmp_path):
    configured_dir = tmp_path / "missing"
    configured_dir.mkdir(parents=True, exist_ok=True)
    configured_path = configured_dir / "credentials.json"

    fallback_dir = tmp_path / ".claude"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    fallback_file = fallback_dir / ".credentials.json"
    fallback_file.write_text('{"api_key": "should-not-be-used"}', encoding="utf-8")

    apply_config(
        monkeypatch,
        CLAUDE_CLI_USE_CREDENTIALS=True,
        CLAUDE_CLI_CREDENTIALS_FILE=str(configured_path),
    )

    assert Config.get_claude_cli_api_key() is None


def test_claude_cli_api_key_supports_windows_style_explicit_path(monkeypatch, tmp_path):
    credentials_dir = tmp_path / ".claude"
    credentials_dir.mkdir(parents=True, exist_ok=True)
    credentials_file = credentials_dir / ".credentials.json"
    credentials_file.write_text('{"api_key": "windows-claude-key"}', encoding="utf-8")

    apply_config(
        monkeypatch,
        CLAUDE_CLI_USE_CREDENTIALS=True,
        CLAUDE_CLI_CREDENTIALS_FILE=str(credentials_file),
    )

    assert Config.get_claude_cli_api_key() == "windows-claude-key"


def test_claude_cli_api_key_supports_claude_code_oauth_schema(monkeypatch, tmp_path):
    credentials_dir = tmp_path / ".claude"
    credentials_dir.mkdir(parents=True, exist_ok=True)
    credentials_file = credentials_dir / ".credentials.json"
    credentials_file.write_text(
        '{"claudeAiOauth": {"accessToken": "oauth-claude-token"}}',
        encoding="utf-8",
    )

    apply_config(
        monkeypatch,
        CLAUDE_CLI_USE_CREDENTIALS=True,
        CLAUDE_CLI_CREDENTIALS_FILE=str(credentials_file),
    )

    assert Config.get_claude_cli_api_key() == "oauth-claude-token"


def test_validate_allows_claude_cli_for_anthropic_provider(monkeypatch):
    overrides = {
        **base_overrides(),
        "LLM_PROVIDER": "anthropic",
        "SEARCH_PROVIDER": "anthropic",
        "GRAPHITI_LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "",
        "GRAPHITI_LLM_API_KEY": "",
        "CLAUDE_CLI_USE_CREDENTIALS": True,
        "GRAPHITI_EMBEDDER_PROVIDER": "ollama",
        "GRAPHITI_EMBEDDER_BASE_URL": "http://localhost:11434/v1",
        "GRAPHITI_EMBEDDER_MODEL": "nomic-embed-text",
        "GRAPHITI_RERANKER_PROVIDER": "ollama",
        "GRAPHITI_RERANKER_BASE_URL": "http://localhost:11434/v1",
        "GRAPHITI_RERANKER_MODEL": "nomic-embed-text",
    }
    apply_config(
        monkeypatch,
        **overrides,
    )
    assert Config.validate() == []


def test_anthropic_provider_uses_claude_cli_when_configured(monkeypatch):
    apply_config(
        monkeypatch,
        CLAUDE_CLI_USE_CREDENTIALS=True,
        CLAUDE_CLI_COMMAND="claude",
        ANTHROPIC_API_KEY="",
    )

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[:3] == ["claude", "auth", "status"]:
            return SimpleNamespace(returncode=0, stdout="logged in", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout='{"type":"result","is_error":false,"result":"hello","usage":{"input_tokens":12,"output_tokens":4}}',
            stderr="",
        )

    monkeypatch.setattr("app.utils.llm_provider.shutil.which", lambda command: command)
    monkeypatch.setattr("app.utils.llm_provider.subprocess.run", fake_run)

    provider = AnthropicProvider()
    response = provider.chat([{"role": "user", "content": "Say hello"}])

    assert isinstance(provider._delegate, ClaudeCliProvider)
    assert response.content == "hello"
    assert response.usage == {
        "prompt_tokens": 12,
        "completion_tokens": 4,
        "total_tokens": 16,
    }
    assert any(command[:3] == ["claude", "auth", "status"] for command in calls)
    assert any(command[0] == "claude" and "-p" in command for command in calls)


def test_claude_cli_provider_returns_json_text_for_chat_json(monkeypatch):
    apply_config(
        monkeypatch,
        CLAUDE_CLI_USE_CREDENTIALS=True,
        CLAUDE_CLI_COMMAND="claude",
    )

    def fake_run(command, **kwargs):
        if command[:3] == ["claude", "auth", "status"]:
            return SimpleNamespace(returncode=0, stdout="logged in", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=(
                '{"type":"result","is_error":false,"result":"```json\\n{\\"ok\\": true}\\n```",'
                '"usage":{"input_tokens":8,"output_tokens":3}}'
            ),
            stderr="",
        )

    monkeypatch.setattr("app.utils.llm_provider.shutil.which", lambda command: command)
    monkeypatch.setattr("app.utils.llm_provider.subprocess.run", fake_run)

    provider = ClaudeCliProvider(model="claude-sonnet-4-6")
    response = provider.chat(
        [{"role": "system", "content": "Return JSON"}, {"role": "user", "content": "Say ok"}],
        response_format={"type": "json_object"},
    )

    assert response.content == '{"ok": true}'
    assert response.usage == {
        "prompt_tokens": 8,
        "completion_tokens": 3,
        "total_tokens": 11,
    }


def test_graphiti_uses_claude_cli_client_when_configured(monkeypatch):
    overrides = {
        **base_overrides(),
        "GRAPHITI_LLM_PROVIDER": "anthropic",
        "GRAPHITI_LLM_MODEL": "claude-sonnet-4-6",
        "CLAUDE_CLI_USE_CREDENTIALS": True,
    }
    apply_config(monkeypatch, **overrides)

    monkeypatch.setattr("app.utils.llm_provider.shutil.which", lambda command: command)
    monkeypatch.setattr(
        "app.utils.llm_provider.subprocess.run",
        lambda command, **kwargs: SimpleNamespace(returncode=0, stdout="logged in", stderr=""),
    )

    client = create_graphiti_llm_client()

    assert client.__class__.__name__ == "GraphitiClaudeCliClient"


def test_graphiti_claude_cli_client_normalizes_attribute_wrapper(monkeypatch):
    apply_config(
        monkeypatch,
        **{
            **base_overrides(),
            "GRAPHITI_LLM_PROVIDER": "anthropic",
            "GRAPHITI_LLM_MODEL": "claude-sonnet-4-6",
            "CLAUDE_CLI_USE_CREDENTIALS": True,
        },
    )

    def fake_run(command, **kwargs):
        if command[:3] == ["claude", "auth", "status"]:
            return SimpleNamespace(returncode=0, stdout="logged in", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=(
                '{"type":"result","is_error":false,"result":"","structured_output":'
                '{"name":"ExampleCo","entity_types":["Entity","Company"],'
                '"attributes":{"core_features":"QR-enabled packaging"}},'
                '"usage":{"input_tokens":5,"output_tokens":2}}'
            ),
            stderr="",
        )

    monkeypatch.setattr("app.utils.llm_provider.shutil.which", lambda command: command)
    monkeypatch.setattr("app.utils.llm_provider.subprocess.run", fake_run)

    client = create_graphiti_llm_client()
    Company = create_model("Company", core_features=(str | None, None))
    result = asyncio.run(client.generate_response(
        [
            Message(role="system", content="Return JSON only."),
            Message(role="user", content="Extract company attributes."),
        ],
        response_model=Company,
        max_tokens=512,
    ))

    assert result == {"core_features": "QR-enabled packaging"}


def test_graphiti_claude_cli_client_uses_json_schema_for_required_edge_fields(monkeypatch):
    apply_config(
        monkeypatch,
        **{
            **base_overrides(),
            "GRAPHITI_LLM_PROVIDER": "anthropic",
            "GRAPHITI_LLM_MODEL": "claude-sonnet-4-6",
            "CLAUDE_CLI_USE_CREDENTIALS": True,
        },
    )

    observed_commands = []

    def fake_run(command, **kwargs):
        observed_commands.append(command)
        if command[:3] == ["claude", "auth", "status"]:
            return SimpleNamespace(returncode=0, stdout="logged in", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout=(
                '{"type":"result","is_error":false,"result":"","structured_output":'
                '{"duplicate_facts":[],"contradicted_facts":[]},'
                '"usage":{"input_tokens":7,"output_tokens":3}}'
            ),
            stderr="",
        )

    monkeypatch.setattr("app.utils.llm_provider.shutil.which", lambda command: command)
    monkeypatch.setattr("app.utils.llm_provider.subprocess.run", fake_run)

    client = create_graphiti_llm_client()
    result = asyncio.run(client.generate_response(
        [
            Message(role="system", content="Return JSON only."),
            Message(role="user", content="Compare facts."),
        ],
        response_model=EdgeDuplicate,
        max_tokens=512,
    ))

    assert result == {"duplicate_facts": [], "contradicted_facts": []}
    assert any("--json-schema" in command for command in observed_commands)
