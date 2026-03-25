import pytest

from app.utils.openai_compatible import (
    get_default_base_url,
    is_local_base_url,
    resolve_openai_compatible_api_key,
)


def test_is_local_base_url_recognizes_local_hosts():
    assert is_local_base_url("http://localhost:11434/v1") is True
    assert is_local_base_url("http://127.0.0.1:1234/v1") is True
    assert is_local_base_url("https://api.openai.com/v1") is False


def test_default_base_urls_cover_local_vector_backends():
    assert get_default_base_url("ollama") == "http://localhost:11434/v1"
    assert get_default_base_url("lmstudio") == "http://localhost:1234/v1"


def test_local_openai_compatible_server_uses_placeholder_key():
    resolved_key = resolve_openai_compatible_api_key(
        api_key=None,
        base_url="http://localhost:11434/v1",
        provider_name="ollama",
    )
    assert resolved_key == "ollama"


def test_remote_openai_requires_real_key():
    with pytest.raises(ValueError):
        resolve_openai_compatible_api_key(
            api_key=None,
            base_url="https://api.openai.com/v1",
            provider_name="openai",
        )
