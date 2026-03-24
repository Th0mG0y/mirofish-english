from __future__ import annotations

from urllib.parse import urlparse


_LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "host.docker.internal",
}

_DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}

_DEFAULT_API_KEYS = {
    "ollama": "ollama",
    "lmstudio": "lm-studio",
}


def is_local_base_url(base_url: str | None) -> bool:
    if not base_url:
        return False

    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()
    return hostname in _LOCAL_HOSTS


def get_default_base_url(provider_name: str, fallback: str | None = None) -> str | None:
    normalized_name = provider_name.lower()
    return _DEFAULT_BASE_URLS.get(normalized_name, fallback)


def get_default_api_key(provider_name: str, fallback: str | None = None) -> str | None:
    normalized_name = provider_name.lower()
    return _DEFAULT_API_KEYS.get(normalized_name, fallback)


def resolve_openai_compatible_api_key(
    api_key: str | None,
    base_url: str | None,
    provider_name: str = "openai",
    fallback: str | None = None,
) -> str:
    if api_key:
        return api_key
    if fallback:
        return fallback
    if is_local_base_url(base_url):
        return get_default_api_key(provider_name, "local-openai-compatible") or "local-openai-compatible"
    raise ValueError("OpenAI-compatible API key is not configured")
