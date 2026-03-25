"""
Configuration management
Unified loading of configuration from the .env file in the project root directory
"""

import json
import os
from dotenv import load_dotenv

from .utils.openai_compatible import (
    get_default_base_url,
    resolve_openai_compatible_api_key,
)

# Load .env file from the project root directory
# Path: MiroFish/.env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If no .env in root directory, try loading environment variables (for production)
    load_dotenv(override=True)


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default

    normalized_value = value.strip()
    if not normalized_value or normalized_value.startswith('#'):
        return default

    return normalized_value


def _expand_env_path(path: str | None) -> str | None:
    if not path:
        return None
    return os.path.expanduser(os.path.expandvars(path))


def _load_json_credentials(path: str | None) -> dict:
    resolved_path = _expand_env_path(path)
    if not resolved_path or not os.path.exists(resolved_path):
        return {}

    try:
        with open(resolved_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}

    return {}


def _extract_first_string(data: dict, candidate_paths: list[tuple[str, ...]]) -> str | None:
    for candidate_path in candidate_paths:
        current = data
        for part in candidate_path:
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if isinstance(current, str) and current.strip():
            return current.strip()
    return None


_OPENAI_CLI_KEY_CANDIDATES = [
    ("api_key",),
    ("apiKey",),
    ("openai_api_key",),
    ("openaiApiKey",),
    ("credentials", "api_key"),
    ("credentials", "apiKey"),
    ("auth", "api_key"),
    ("auth", "apiKey"),
]

_CLAUDE_CLI_KEY_CANDIDATES = [
    ("api_key",),
    ("apiKey",),
    ("anthropic_api_key",),
    ("anthropicApiKey",),
    ("claudeAiOauth", "accessToken"),
    ("claude_ai_oauth", "access_token"),
    ("oauth", "accessToken"),
    ("oauth", "access_token"),
    ("credentials", "api_key"),
    ("credentials", "apiKey"),
    ("credentials", "anthropic_api_key"),
    ("credentials", "anthropicApiKey"),
]


class Config:
    """Flask configuration class"""

    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

    # JSON configuration - disable ASCII escaping, allow non-ASCII characters to display directly (instead of \uXXXX format)
    JSON_AS_ASCII = False

    # Multi-provider LLM configuration
    LLM_PROVIDER = _get_env('MIROFISH_LLM_PROVIDER', 'openai').lower()
    LLM_API_KEY = _get_env('LLM_API_KEY')
    LLM_BASE_URL = _get_env('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = _get_env('LLM_MODEL_NAME', 'gpt-5.4-mini')
    ANTHROPIC_API_KEY = _get_env('ANTHROPIC_API_KEY')
    ANTHROPIC_MODEL_NAME = _get_env('ANTHROPIC_MODEL_NAME', 'claude-sonnet-4-6')
    OPENAI_CLI_USE_CREDENTIALS = _get_env('OPENAI_CLI_USE_CREDENTIALS', 'false').lower() == 'true'
    OPENAI_CLI_CREDENTIALS_FILE = _expand_env_path(
        _get_env('OPENAI_CLI_CREDENTIALS_FILE', os.path.join('~', '.codex', 'auth.json'))
    )
    CLAUDE_CLI_USE_CREDENTIALS = _get_env('CLAUDE_CLI_USE_CREDENTIALS', 'false').lower() == 'true'
    CLAUDE_CLI_COMMAND = _get_env('CLAUDE_CLI_COMMAND', 'claude')
    CLAUDE_CLI_CREDENTIALS_FILE = _expand_env_path(
        _get_env('CLAUDE_CLI_CREDENTIALS_FILE')
    )
    CLAUDE_CLI_PERMISSION_MODE = _get_env('CLAUDE_CLI_PERMISSION_MODE', 'plan')
    CLAUDE_CLI_TIMEOUT_SECONDS = int(os.environ.get('CLAUDE_CLI_TIMEOUT_SECONDS', '180'))

    # Ollama configuration
    OLLAMA_API_KEY = _get_env('OLLAMA_API_KEY')  # For Ollama cloud web search
    OLLAMA_BASE_URL = _get_env('OLLAMA_BASE_URL', 'http://localhost:11434/v1')
    OLLAMA_MODEL_NAME = _get_env('OLLAMA_MODEL_NAME', '')  # Falls back to LLM_MODEL_NAME

    # Neo4j configuration
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'password')

    # Some untouched routes still gate on this before reaching the Graphiti-backed services.
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY') or (
        'graphiti-local'
        if NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD
        else None
    )

    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing configuration
    DEFAULT_CHUNK_SIZE = 500  # Default chunk size
    DEFAULT_CHUNK_OVERLAP = 50  # Default overlap size

    # OASIS simulation configuration
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    # OASIS platform available actions configuration
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    # Report Agent configuration
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    # Localization configuration
    MIROFISH_TIMEZONE = os.environ.get('MIROFISH_TIMEZONE', 'us_eastern')
    MIROFISH_LOCALE = os.environ.get('MIROFISH_LOCALE', 'en-US')
    MIROFISH_REGION = os.environ.get('MIROFISH_REGION', 'US')

    # Search configuration
    SEARCH_PROVIDER = _get_env('MIROFISH_SEARCH_PROVIDER', LLM_PROVIDER).lower()
    SEARCH_MODEL = _get_env('MIROFISH_SEARCH_MODEL', '')
    MIROFISH_MAX_SEARCHES_PER_AGENT = int(os.environ.get('MIROFISH_MAX_SEARCHES_PER_AGENT', '5'))
    MIROFISH_ENABLE_SEARCH_ENRICHMENT = os.environ.get('MIROFISH_ENABLE_SEARCH_ENRICHMENT', 'false').lower() == 'true'
    MIROFISH_NEWS_INJECTION_INTERVAL = int(os.environ.get('MIROFISH_NEWS_INJECTION_INTERVAL', '0'))

    # Graphiti configuration
    GRAPHITI_LLM_PROVIDER = _get_env('GRAPHITI_LLM_PROVIDER', LLM_PROVIDER).lower()
    GRAPHITI_LLM_API_KEY = _get_env('GRAPHITI_LLM_API_KEY')
    GRAPHITI_LLM_BASE_URL = _get_env('GRAPHITI_LLM_BASE_URL', '')
    GRAPHITI_LLM_MODEL = _get_env('GRAPHITI_LLM_MODEL', '')
    GRAPHITI_EMBEDDER_PROVIDER = _get_env(
        'GRAPHITI_EMBEDDER_PROVIDER',
        'ollama' if GRAPHITI_LLM_PROVIDER == 'anthropic' else 'openai'
    ).lower()
    GRAPHITI_EMBEDDER_API_KEY = _get_env('GRAPHITI_EMBEDDER_API_KEY')
    GRAPHITI_EMBEDDER_BASE_URL = _get_env('GRAPHITI_EMBEDDER_BASE_URL', '')
    GRAPHITI_EMBEDDER_MODEL = _get_env(
        'GRAPHITI_EMBEDDER_MODEL',
        'text-embedding-3-small'
        if GRAPHITI_EMBEDDER_PROVIDER == 'openai'
        else 'nomic-embed-text'
    )
    GRAPHITI_RERANKER_PROVIDER = _get_env(
        'GRAPHITI_RERANKER_PROVIDER',
        GRAPHITI_EMBEDDER_PROVIDER
    ).lower()
    GRAPHITI_RERANKER_API_KEY = _get_env('GRAPHITI_RERANKER_API_KEY')
    GRAPHITI_RERANKER_BASE_URL = _get_env('GRAPHITI_RERANKER_BASE_URL', '')
    GRAPHITI_RERANKER_MODEL = _get_env(
        'GRAPHITI_RERANKER_MODEL',
        LLM_MODEL_NAME
        if GRAPHITI_RERANKER_PROVIDER == 'openai'
        else GRAPHITI_EMBEDDER_MODEL
    )

    @classmethod
    def get_openai_compatible_model(cls, explicit_model: str | None = None) -> str:
        return explicit_model or cls.LLM_MODEL_NAME

    @classmethod
    def get_openai_cli_api_key(cls) -> str | None:
        if not cls.OPENAI_CLI_USE_CREDENTIALS:
            return None
        data = _load_json_credentials(cls.OPENAI_CLI_CREDENTIALS_FILE)
        return _extract_first_string(data, _OPENAI_CLI_KEY_CANDIDATES)

    @classmethod
    def get_claude_cli_api_key(cls) -> str | None:
        if not cls.CLAUDE_CLI_USE_CREDENTIALS:
            return None
        data = _load_json_credentials(cls.CLAUDE_CLI_CREDENTIALS_FILE)
        return _extract_first_string(data, _CLAUDE_CLI_KEY_CANDIDATES)

    @classmethod
    def is_claude_cli_oauth_token(cls, token: str | None = None) -> bool:
        resolved = token if token is not None else cls.get_claude_cli_api_key()
        if not resolved:
            return False
        return resolved.startswith('sk-ant-oat') or resolved.startswith('sk-ant-aat')

    @classmethod
    def use_claude_cli_for_anthropic(cls) -> bool:
        return cls.CLAUDE_CLI_USE_CREDENTIALS

    @classmethod
    def get_provider_model(cls, provider_name: str, explicit_model: str | None = None) -> str:
        provider_name = provider_name.lower()
        if explicit_model:
            return explicit_model
        if provider_name == 'anthropic':
            return cls.ANTHROPIC_MODEL_NAME
        if provider_name == 'ollama':
            return cls.OLLAMA_MODEL_NAME or cls.LLM_MODEL_NAME
        if provider_name == 'openai':
            return cls.LLM_MODEL_NAME
        raise ValueError(f"Unsupported provider: {provider_name}")

    @classmethod
    def get_graphiti_llm_model(cls) -> str:
        return cls.get_provider_model(cls.GRAPHITI_LLM_PROVIDER, cls.GRAPHITI_LLM_MODEL or None)

    @classmethod
    def get_main_openai_compatible_api_key(cls) -> str:
        return resolve_openai_compatible_api_key(
            api_key=cls.LLM_API_KEY or cls.get_openai_cli_api_key(),
            base_url=cls.LLM_BASE_URL,
            provider_name='openai',
        )

    @classmethod
    def get_graphiti_llm_api_key(cls) -> str:
        if cls.GRAPHITI_LLM_PROVIDER == 'anthropic':
            api_key = cls.GRAPHITI_LLM_API_KEY or cls.ANTHROPIC_API_KEY
            if api_key:
                return api_key

            cli_token = cls.get_claude_cli_api_key()
            if cls.is_claude_cli_oauth_token(cli_token):
                raise ValueError(
                    "Claude CLI OAuth access tokens are not supported by Anthropic API requests. "
                    "Set GRAPHITI_LLM_API_KEY or ANTHROPIC_API_KEY instead."
                )
            api_key = cli_token
            if not api_key:
                raise ValueError("Graphiti Anthropic API key is not configured")
            return api_key

        if cls.GRAPHITI_LLM_PROVIDER == 'ollama':
            return resolve_openai_compatible_api_key(
                api_key=cls.GRAPHITI_LLM_API_KEY,
                base_url=cls.GRAPHITI_LLM_BASE_URL or cls.OLLAMA_BASE_URL,
                provider_name='ollama',
            )

        return resolve_openai_compatible_api_key(
            api_key=cls.GRAPHITI_LLM_API_KEY or cls.LLM_API_KEY or cls.get_openai_cli_api_key(),
            base_url=cls.GRAPHITI_LLM_BASE_URL or cls.LLM_BASE_URL,
            provider_name='openai',
        )

    @classmethod
    def get_graphiti_openai_compatible_base_url(cls, provider_name: str, explicit_base_url: str | None = None) -> str:
        normalized_name = provider_name.lower()
        if explicit_base_url:
            return explicit_base_url
        if normalized_name == 'openai':
            return cls.LLM_BASE_URL
        return get_default_base_url(normalized_name, cls.LLM_BASE_URL) or cls.LLM_BASE_URL

    @classmethod
    def get_graphiti_openai_compatible_api_key(
        cls,
        provider_name: str,
        explicit_api_key: str | None = None,
        explicit_base_url: str | None = None,
    ) -> str:
        base_url = cls.get_graphiti_openai_compatible_base_url(provider_name, explicit_base_url)
        fallback = cls.LLM_API_KEY if provider_name.lower() == 'openai' else None
        if provider_name.lower() == 'openai' and not fallback:
            fallback = cls.get_openai_cli_api_key()
        return resolve_openai_compatible_api_key(
            api_key=explicit_api_key,
            base_url=base_url,
            provider_name=provider_name,
            fallback=fallback,
        )

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        supported_providers = {'openai', 'anthropic', 'ollama'}
        supported_graphiti_vector_providers = {'openai', 'ollama', 'lmstudio'}

        if cls.LLM_PROVIDER not in supported_providers:
            errors.append("MIROFISH_LLM_PROVIDER must be one of: openai, anthropic, ollama")
        if cls.SEARCH_PROVIDER not in supported_providers:
            errors.append("MIROFISH_SEARCH_PROVIDER must be one of: openai, anthropic, ollama")
        if cls.GRAPHITI_LLM_PROVIDER not in supported_providers:
            errors.append("GRAPHITI_LLM_PROVIDER must be one of: openai, anthropic, ollama")
        if cls.GRAPHITI_EMBEDDER_PROVIDER not in supported_graphiti_vector_providers:
            errors.append("GRAPHITI_EMBEDDER_PROVIDER must be one of: openai, ollama, lmstudio")
        if cls.GRAPHITI_RERANKER_PROVIDER not in supported_graphiti_vector_providers:
            errors.append("GRAPHITI_RERANKER_PROVIDER must be one of: openai, ollama, lmstudio")

        if cls.LLM_PROVIDER == 'openai':
            try:
                cls.get_main_openai_compatible_api_key()
            except ValueError:
                errors.append("LLM_API_KEY is not configured (required when MIROFISH_LLM_PROVIDER=openai unless LLM_BASE_URL points to a local OpenAI-compatible server)")
        if cls.LLM_PROVIDER == 'anthropic':
            if cls.use_claude_cli_for_anthropic():
                pass
            elif cls.ANTHROPIC_API_KEY:
                pass
            elif not cls.get_claude_cli_api_key():
                errors.append("ANTHROPIC_API_KEY is not configured (required when MIROFISH_LLM_PROVIDER=anthropic)")
        # ollama provider needs no API key for local inference (key auto-resolves to "ollama")

        if cls.SEARCH_PROVIDER == 'openai':
            try:
                cls.get_main_openai_compatible_api_key()
            except ValueError:
                errors.append("LLM_API_KEY is not configured (required when MIROFISH_SEARCH_PROVIDER=openai unless LLM_BASE_URL points to a local OpenAI-compatible server)")
        if cls.SEARCH_PROVIDER == 'anthropic':
            if cls.use_claude_cli_for_anthropic():
                pass
            elif cls.ANTHROPIC_API_KEY:
                pass
            elif not cls.get_claude_cli_api_key():
                errors.append("ANTHROPIC_API_KEY is not configured (required when MIROFISH_SEARCH_PROVIDER=anthropic)")
        # ollama search provider: OLLAMA_API_KEY is optional (only needed for cloud web search)

        if cls.GRAPHITI_LLM_PROVIDER == 'anthropic' and cls.use_claude_cli_for_anthropic():
            pass
        else:
            try:
                cls.get_graphiti_llm_api_key()
            except ValueError:
                if cls.GRAPHITI_LLM_PROVIDER == 'anthropic':
                    errors.append("ANTHROPIC_API_KEY or GRAPHITI_LLM_API_KEY is not configured (required when GRAPHITI_LLM_PROVIDER=anthropic)")
                else:
                    errors.append("LLM_API_KEY or GRAPHITI_LLM_API_KEY is not configured (required when GRAPHITI_LLM_PROVIDER=openai unless the Graphiti LLM base URL points to a local OpenAI-compatible server)")

        try:
            cls.get_graphiti_openai_compatible_api_key(
                cls.GRAPHITI_EMBEDDER_PROVIDER,
                cls.GRAPHITI_EMBEDDER_API_KEY,
                cls.GRAPHITI_EMBEDDER_BASE_URL or None,
            )
        except ValueError:
            errors.append("Graphiti embedder credentials are not configured")

        try:
            cls.get_graphiti_openai_compatible_api_key(
                cls.GRAPHITI_RERANKER_PROVIDER,
                cls.GRAPHITI_RERANKER_API_KEY,
                cls.GRAPHITI_RERANKER_BASE_URL or None,
            )
        except ValueError:
            errors.append("Graphiti reranker credentials are not configured")

        if not cls.NEO4J_URI or not cls.NEO4J_USER or not cls.NEO4J_PASSWORD:
            errors.append("NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD must be configured for Graphiti")
        return errors
