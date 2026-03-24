"""
Configuration management
Unified loading of configuration from the .env file in the project root directory
"""

import os
from dotenv import load_dotenv

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

    # LLM configuration (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

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

    # Multi-provider LLM configuration
    LLM_PROVIDER = os.environ.get('MIROFISH_LLM_PROVIDER', 'openai')
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    ANTHROPIC_MODEL_NAME = os.environ.get('ANTHROPIC_MODEL_NAME', 'claude-sonnet-4-6')

    # Search configuration
    SEARCH_PROVIDER = os.environ.get('MIROFISH_SEARCH_PROVIDER', 'openai')
    SEARCH_MODEL = os.environ.get('MIROFISH_SEARCH_MODEL', '')
    MIROFISH_MAX_SEARCHES_PER_AGENT = int(os.environ.get('MIROFISH_MAX_SEARCHES_PER_AGENT', '5'))
    MIROFISH_ENABLE_SEARCH_ENRICHMENT = os.environ.get('MIROFISH_ENABLE_SEARCH_ENRICHMENT', 'false').lower() == 'true'
    MIROFISH_NEWS_INJECTION_INTERVAL = int(os.environ.get('MIROFISH_NEWS_INJECTION_INTERVAL', '0'))

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        # Only require LLM_API_KEY when using the OpenAI provider
        if cls.LLM_PROVIDER == 'openai' and not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY is not configured (required when MIROFISH_LLM_PROVIDER=openai)")
        if cls.LLM_PROVIDER == 'anthropic' and not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is not configured (required when MIROFISH_LLM_PROVIDER=anthropic)")
        if not cls.NEO4J_URI or not cls.NEO4J_USER or not cls.NEO4J_PASSWORD:
            errors.append("NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD must be configured for Graphiti")
        return errors
