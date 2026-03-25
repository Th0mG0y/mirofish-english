"""
Utilities module
"""

__all__ = ['FileParser', 'LLMClient']


def __getattr__(name):
    if name == 'FileParser':
        from .file_parser import FileParser
        return FileParser
    if name == 'LLMClient':
        from .llm_client import LLMClient
        return LLMClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

