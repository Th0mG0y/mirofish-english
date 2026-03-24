"""
LLM client wrapper
Unified call interface using the OpenAI format, with optional provider delegation
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM client — delegates to LLMProvider when available, falls back to direct OpenAI"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        provider=None
    ):
        self._provider = provider  # Optional LLMProvider instance

        if self._provider is not None:
            # When using a provider, we don't need OpenAI client directly
            self.api_key = ""
            self.base_url = ""
            self.model = getattr(provider, 'model', model or Config.LLM_MODEL_NAME)
            self.client = None
        elif api_key is None and Config.LLM_PROVIDER != 'openai':
            # No explicit API key given and not using OpenAI — delegate to the configured provider
            from .llm_provider import ProviderFactory
            self._provider = ProviderFactory.create_from_config()
            self.api_key = ""
            self.base_url = ""
            self.model = getattr(self._provider, 'model', model or Config.LLM_MODEL_NAME)
            self.client = None
        else:
            self.api_key = api_key or Config.LLM_API_KEY
            self.base_url = base_url or Config.LLM_BASE_URL
            self.model = model or Config.LLM_MODEL_NAME

            if not self.api_key:
                raise ValueError("LLM_API_KEY is not configured")

            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        Send a chat request

        Args:
            messages: List of messages
            temperature: Temperature parameter
            max_tokens: Maximum number of tokens
            response_format: Response format (e.g. JSON mode)

        Returns:
            Model response text
        """
        # Delegate to provider if available
        if self._provider is not None:
            result = self._provider.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format
            )
            return result.content

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # Some models (e.g. MiniMax M2.5) include <think> reasoning content in the response; strip it out
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content

    def web_search(self, query: str, context: str = ""):
        """
        Perform a web search using the configured search provider.

        Returns:
            WebSearchResult with answer and citations
        """
        if self._provider is not None and self._provider.supports_web_search():
            return self._provider.web_search(query=query, context=context)

        # Fallback: create search provider on the fly
        from .llm_provider import ProviderFactory
        search_provider = ProviderFactory.create_search_provider()
        return search_provider.web_search(query=query, context=context)

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send a chat request and return JSON

        Args:
            messages: List of messages
            temperature: Temperature parameter
            max_tokens: Maximum number of tokens

        Returns:
            Parsed JSON object
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        # Strip markdown code block markers
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON returned by LLM: {cleaned_response}")
