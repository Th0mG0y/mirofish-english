"""
Configuration management
Unified loading of configuration from the .env file in the project root directory
"""

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


class Config:
    """Flask configuration class"""

    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

    # JSON configuration - disable ASCII escaping, allow non-ASCII characters to display directly (instead of \uXXXX format)
    JSON_AS_ASCII = False

    # Multi-provider LLM configuration
    LLM_PROVIDER = os.environ.get('MIROFISH_LLM_PROVIDER', 'openai').lower()
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-5.4-mini')
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    ANTHROPIC_MODEL_NAME = os.environ.get('ANTHROPIC_MODEL_NAME', 'claude-sonnet-4-6')

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
    SEARCH_PROVIDER = os.environ.get('MIROFISH_SEARCH_PROVIDER', LLM_PROVIDER).lower()
    SEARCH_MODEL = os.environ.get('MIROFISH_SEARCH_MODEL', '')
    MIROFISH_MAX_SEARCHES_PER_AGENT = int(os.environ.get('MIROFISH_MAX_SEARCHES_PER_AGENT', '5'))
    MIROFISH_ENABLE_SEARCH_ENRICHMENT = os.environ.get('MIROFISH_ENABLE_SEARCH_ENRICHMENT', 'false').lower() == 'true'
    MIROFISH_NEWS_INJECTION_INTERVAL = int(os.environ.get('MIROFISH_NEWS_INJECTION_INTERVAL', '0'))

    # Graphiti configuration
    GRAPHITI_LLM_PROVIDER = os.environ.get('GRAPHITI_LLM_PROVIDER', LLM_PROVIDER).lower()
    GRAPHITI_LLM_API_KEY = os.environ.get('GRAPHITI_LLM_API_KEY')
    GRAPHITI_LLM_BASE_URL = os.environ.get('GRAPHITI_LLM_BASE_URL', '')
    GRAPHITI_LLM_MODEL = os.environ.get('GRAPHITI_LLM_MODEL', '')
    GRAPHITI_EMBEDDER_PROVIDER = os.environ.get(
        'GRAPHITI_EMBEDDER_PROVIDER',
        'ollama' if GRAPHITI_LLM_PROVIDER == 'anthropic' else 'openai'
    ).lower()
    GRAPHITI_EMBEDDER_API_KEY = os.environ.get('GRAPHITI_EMBEDDER_API_KEY')
    GRAPHITI_EMBEDDER_BASE_URL = os.environ.get('GRAPHITI_EMBEDDER_BASE_URL', '')
    GRAPHITI_EMBEDDER_MODEL = os.environ.get(
        'GRAPHITI_EMBEDDER_MODEL',
        'text-embedding-3-small'
        if GRAPHITI_EMBEDDER_PROVIDER == 'openai'
        else 'nomic-embed-text'
    )
    GRAPHITI_RERANKER_PROVIDER = os.environ.get(
        'GRAPHITI_RERANKER_PROVIDER',
        GRAPHITI_EMBEDDER_PROVIDER
    ).lower()
    GRAPHITI_RERANKER_API_KEY = os.environ.get('GRAPHITI_RERANKER_API_KEY')
    GRAPHITI_RERANKER_BASE_URL = os.environ.get('GRAPHITI_RERANKER_BASE_URL', '')
    GRAPHITI_RERANKER_MODEL = os.environ.get(
        'GRAPHITI_RERANKER_MODEL',
        LLM_MODEL_NAME
        if GRAPHITI_RERANKER_PROVIDER == 'openai'
        else GRAPHITI_EMBEDDER_MODEL
    )

    @classmethod
    def get_openai_compatible_model(cls, explicit_model: str | None = None) -> str:
        return explicit_model or cls.LLM_MODEL_NAME

    @classmethod
    def get_provider_model(cls, provider_name: str, explicit_model: str | None = None) -> str:
        provider_name = provider_name.lower()
        if explicit_model:
            return explicit_model
        if provider_name == 'anthropic':
            return cls.ANTHROPIC_MODEL_NAME
        if provider_name == 'openai':
            return cls.LLM_MODEL_NAME
        raise ValueError(f"Unsupported provider: {provider_name}")

    @classmethod
    def get_graphiti_llm_model(cls) -> str:
        return cls.get_provider_model(cls.GRAPHITI_LLM_PROVIDER, cls.GRAPHITI_LLM_MODEL or None)

    @classmethod
    def get_main_openai_compatible_api_key(cls) -> str:
        return resolve_openai_compatible_api_key(
            api_key=cls.LLM_API_KEY,
            base_url=cls.LLM_BASE_URL,
            provider_name='openai',
        )

    @classmethod
    def get_graphiti_llm_api_key(cls) -> str:
        if cls.GRAPHITI_LLM_PROVIDER == 'anthropic':
            api_key = cls.GRAPHITI_LLM_API_KEY or cls.ANTHROPIC_API_KEY
            if not api_key:
                raise ValueError("Graphiti Anthropic API key is not configured")
            return api_key

        return resolve_openai_compatible_api_key(
            api_key=cls.GRAPHITI_LLM_API_KEY or cls.LLM_API_KEY,
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
        supported_remote_providers = {'openai', 'anthropic'}
        supported_graphiti_vector_providers = {'openai', 'ollama', 'lmstudio'}

        if cls.LLM_PROVIDER not in supported_remote_providers:
            errors.append("MIROFISH_LLM_PROVIDER must be one of: openai, anthropic")
        if cls.SEARCH_PROVIDER not in supported_remote_providers:
            errors.append("MIROFISH_SEARCH_PROVIDER must be one of: openai, anthropic")
        if cls.GRAPHITI_LLM_PROVIDER not in supported_remote_providers:
            errors.append("GRAPHITI_LLM_PROVIDER must be one of: openai, anthropic")
        if cls.GRAPHITI_EMBEDDER_PROVIDER not in supported_graphiti_vector_providers:
            errors.append("GRAPHITI_EMBEDDER_PROVIDER must be one of: openai, ollama, lmstudio")
        if cls.GRAPHITI_RERANKER_PROVIDER not in supported_graphiti_vector_providers:
            errors.append("GRAPHITI_RERANKER_PROVIDER must be one of: openai, ollama, lmstudio")

        if cls.LLM_PROVIDER == 'openai':
            try:
                cls.get_main_openai_compatible_api_key()
            except ValueError:
                errors.append("LLM_API_KEY is not configured (required when MIROFISH_LLM_PROVIDER=openai unless LLM_BASE_URL points to a local OpenAI-compatible server)")
        if cls.LLM_PROVIDER == 'anthropic' and not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is not configured (required when MIROFISH_LLM_PROVIDER=anthropic)")

        if cls.SEARCH_PROVIDER == 'openai':
            try:
                cls.get_main_openai_compatible_api_key()
            except ValueError:
                errors.append("LLM_API_KEY is not configured (required when MIROFISH_SEARCH_PROVIDER=openai unless LLM_BASE_URL points to a local OpenAI-compatible server)")
        if cls.SEARCH_PROVIDER == 'anthropic' and not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is not configured (required when MIROFISH_SEARCH_PROVIDER=anthropic)")

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
