"""
Multi-provider LLM abstraction layer
Supports OpenAI and Anthropic providers with unified interface
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from ..config import Config
from .openai_compatible import is_local_base_url, resolve_openai_compatible_api_key
from ..utils.logger import get_logger

logger = get_logger('mirofish.llm_provider')


@dataclass
class Citation:
    """A citation from web search results"""
    url: str
    title: str
    snippet: str


@dataclass
class WebSearchResult:
    """Result from a web search operation"""
    query: str
    answer: str
    citations: List[Citation] = field(default_factory=list)


@dataclass
class ProviderResponse:
    """Unified response from any LLM provider"""
    content: str
    model: str = ""
    usage: Optional[Dict[str, int]] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
        response_format: Optional[Dict] = None
    ) -> ProviderResponse:
        """Send a chat completion request"""
        pass

    def supports_web_search(self) -> bool:
        """Whether this provider supports built-in web search"""
        return False

    def web_search(
        self,
        query: str,
        context: str = "",
        user_location: Optional[Dict] = None
    ) -> WebSearchResult:
        """Perform a web search using the provider's built-in search capability"""
        raise NotImplementedError("This provider does not support web search")


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        from openai import OpenAI

        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        self.api_key = resolve_openai_compatible_api_key(
            api_key=api_key,
            base_url=self.base_url,
            provider_name='openai',
            fallback=Config.LLM_API_KEY,
        )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        logger.info(f"OpenAIProvider initialized: model={self.model}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
        response_format: Optional[Dict] = None
    ) -> ProviderResponse:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        # Strip <think> tags from reasoning models
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return ProviderResponse(content=content, model=self.model, usage=usage)

    def supports_web_search(self) -> bool:
        return not is_local_base_url(self.base_url)

    def web_search(
        self,
        query: str,
        context: str = "",
        user_location: Optional[Dict] = None
    ) -> WebSearchResult:
        """Use OpenAI's responses API with web_search tool"""
        if is_local_base_url(self.base_url):
            return WebSearchResult(
                query=query,
                answer="Built-in web search is unavailable for local OpenAI-compatible servers. Use Anthropic or the real OpenAI API for search.",
                citations=[],
            )

        try:
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": query})

            response = self.client.responses.create(
                model=self.model,
                tools=[{"type": "web_search"}],
                input=messages
            )

            # Extract text and citations from response
            answer = ""
            citations = []

            for item in response.output:
                if hasattr(item, 'content'):
                    for block in item.content:
                        if hasattr(block, 'text'):
                            answer = block.text
                        if hasattr(block, 'annotations'):
                            for ann in block.annotations:
                                if hasattr(ann, 'url'):
                                    citations.append(Citation(
                                        url=ann.url,
                                        title=getattr(ann, 'title', ''),
                                        snippet=""
                                    ))

            return WebSearchResult(query=query, answer=answer, citations=citations)

        except Exception as e:
            logger.warning(f"OpenAI web search failed: {e}")
            return WebSearchResult(query=query, answer=f"Search failed: {str(e)}", citations=[])


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError("anthropic package is required. Install with: pip install anthropic>=0.40.0")

        self.api_key = api_key or Config.ANTHROPIC_API_KEY
        self.model = model or Config.ANTHROPIC_MODEL_NAME

        if not self.api_key:
            raise ValueError("Anthropic API key is not configured")

        self.client = Anthropic(api_key=self.api_key)
        logger.info(f"AnthropicProvider initialized: model={self.model}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
        response_format: Optional[Dict] = None
    ) -> ProviderResponse:
        # Separate system message from conversation messages
        system_content = ""
        conversation_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                conversation_messages.append(msg)

        # If caller requested JSON output, inject instruction into system prompt
        # (Anthropic ignores OpenAI-style response_format, so we enforce it via the prompt)
        if response_format and response_format.get("type") == "json_object":
            json_instruction = "You must respond with valid JSON only. Do not include any text, explanation, or markdown formatting outside the JSON object."
            system_content = f"{system_content}\n\n{json_instruction}" if system_content else json_instruction

        kwargs = {
            "model": self.model,
            "messages": conversation_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_content:
            kwargs["system"] = system_content

        # Use streaming to avoid Anthropic's 10-minute timeout on long requests
        content = ""
        input_tokens = 0
        output_tokens = 0

        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                content += text
            # Get final message for usage stats
            final_message = stream.get_final_message()
            if final_message and final_message.usage:
                input_tokens = final_message.usage.input_tokens
                output_tokens = final_message.usage.output_tokens

        usage = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        } if (input_tokens or output_tokens) else None

        return ProviderResponse(content=content, model=self.model, usage=usage)

    def supports_web_search(self) -> bool:
        return True

    def web_search(
        self,
        query: str,
        context: str = "",
        user_location: Optional[Dict] = None
    ) -> WebSearchResult:
        """Use Anthropic's built-in web search tool"""
        try:
            messages = [{"role": "user", "content": query}]
            system_content = context if context else "You are a helpful research assistant. Search the web for relevant information."

            max_uses = Config.MIROFISH_MAX_SEARCHES_PER_AGENT

            response = self.client.messages.create(
                model=self.model,
                system=system_content,
                messages=messages,
                max_tokens=4096,
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_uses
                }]
            )

            # Extract text and citations
            answer = ""
            citations = []

            for block in response.content or []:
                if hasattr(block, 'text'):
                    answer += block.text
                    # Parse citation blocks if present
                    for cite in (getattr(block, 'citations', None) or []):
                        citations.append(Citation(
                            url=getattr(cite, 'url', ''),
                            title=getattr(cite, 'title', ''),
                            snippet=getattr(cite, 'cited_text', '')
                        ))

            return WebSearchResult(query=query, answer=answer, citations=citations)

        except Exception as e:
            logger.warning(f"Anthropic web search failed: {e}")
            return WebSearchResult(query=query, answer=f"Search failed: {str(e)}", citations=[])


class OllamaProvider(LLMProvider):
    """Ollama LLM provider — local inference via OpenAI-compatible API, optional cloud web search"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        search_api_key: Optional[str] = None,
    ):
        from openai import OpenAI

        self.base_url = base_url or Config.OLLAMA_BASE_URL
        self.model = model or Config.OLLAMA_MODEL_NAME or Config.LLM_MODEL_NAME
        self.api_key = resolve_openai_compatible_api_key(
            api_key=api_key,
            base_url=self.base_url,
            provider_name='ollama',
        )
        self.search_api_key = search_api_key or Config.OLLAMA_API_KEY

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        logger.info(f"OllamaProvider initialized: model={self.model}, base_url={self.base_url}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
        response_format: Optional[Dict] = None
    ) -> ProviderResponse:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Try native JSON mode first; inject prompt instruction as fallback
        if response_format and response_format.get("type") == "json_object":
            try:
                kwargs["response_format"] = response_format
                response = self.client.chat.completions.create(**kwargs)
            except Exception:
                # Model may not support response_format — fall back to prompt injection
                del kwargs["response_format"]
                json_instruction = "You must respond with valid JSON only. Do not include any text, explanation, or markdown formatting outside the JSON object."
                patched = False
                for msg in kwargs["messages"]:
                    if msg["role"] == "system":
                        msg["content"] += f"\n\n{json_instruction}"
                        patched = True
                        break
                if not patched:
                    kwargs["messages"] = [{"role": "system", "content": json_instruction}] + kwargs["messages"]
                response = self.client.chat.completions.create(**kwargs)
        else:
            if response_format:
                kwargs["response_format"] = response_format
            response = self.client.chat.completions.create(**kwargs)

        content = response.choices[0].message.content or ""
        # Strip <think> tags from reasoning models (e.g. qwen3)
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return ProviderResponse(content=content, model=self.model, usage=usage)

    def supports_web_search(self) -> bool:
        return bool(self.search_api_key)

    def web_search(
        self,
        query: str,
        context: str = "",
        user_location: Optional[Dict] = None
    ) -> WebSearchResult:
        """Use Ollama's cloud web search API (requires OLLAMA_API_KEY)"""
        if not self.search_api_key:
            return WebSearchResult(
                query=query,
                answer="OLLAMA_API_KEY not configured. Set it in .env to enable Ollama cloud web search (free with an Ollama account).",
                citations=[],
            )

        import urllib.request
        import urllib.error

        try:
            payload = json.dumps({"query": query}).encode("utf-8")
            req = urllib.request.Request(
                "https://ollama.com/api/web_search",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.search_api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            citations = []
            for result in data.get("results", []):
                citations.append(Citation(
                    url=result.get("url", ""),
                    title=result.get("title", ""),
                    snippet=result.get("snippet", result.get("content", "")),
                ))

            answer = data.get("answer", "")
            if not answer and citations:
                answer = "\n\n".join(
                    f"**{c.title}**: {c.snippet}" for c in citations if c.snippet
                )

            return WebSearchResult(query=query, answer=answer, citations=citations)

        except urllib.error.HTTPError as e:
            logger.warning(f"Ollama web search HTTP error {e.code}: {e.reason}")
            return WebSearchResult(query=query, answer=f"Ollama web search failed (HTTP {e.code}): {e.reason}", citations=[])
        except Exception as e:
            logger.warning(f"Ollama web search failed: {e}")
            return WebSearchResult(query=query, answer=f"Ollama web search failed: {str(e)}", citations=[])


class ProviderFactory:
    """Factory for creating LLM providers"""

    _providers = {
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
    }

    @classmethod
    def _build_provider_kwargs(
        cls,
        provider_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized_name = provider_name.lower()
        kwargs: Dict[str, Any] = {}

        if model:
            kwargs["model"] = model

        if normalized_name == "openai":
            if api_key is not None:
                kwargs["api_key"] = api_key
            if base_url is not None:
                kwargs["base_url"] = base_url
            return kwargs

        if normalized_name == "anthropic":
            if api_key is not None:
                kwargs["api_key"] = api_key
            return kwargs

        if normalized_name == "ollama":
            if api_key is not None:
                kwargs["api_key"] = api_key
            if base_url is not None:
                kwargs["base_url"] = base_url
            return kwargs

        raise ValueError(f"Unknown provider: {provider_name}. Available: {list(cls._providers.keys())}")

    @classmethod
    def create(cls, provider_name: str, **kwargs) -> LLMProvider:
        """Create a provider by name"""
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}. Available: {list(cls._providers.keys())}")
        return provider_class(**kwargs)

    @classmethod
    def create_from_config(cls) -> LLMProvider:
        """Create the main LLM provider from config"""
        provider_name = Config.LLM_PROVIDER
        logger.info(f"Creating main LLM provider: {provider_name}")
        return cls.create(provider_name)

    @classmethod
    def create_main_provider(
        cls,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> LLMProvider:
        provider_name = Config.LLM_PROVIDER
        kwargs = cls._build_provider_kwargs(
            provider_name,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        logger.info(
            f"Creating main LLM provider: {provider_name}"
            + (f" model={kwargs['model']}" if "model" in kwargs else "")
        )
        return cls.create(provider_name, **kwargs)

    @classmethod
    def create_search_provider(cls) -> LLMProvider:
        """Create the search provider (may differ from main provider)"""
        provider_name = Config.SEARCH_PROVIDER
        search_model = Config.SEARCH_MODEL

        kwargs = cls._build_provider_kwargs(
            provider_name,
            model=search_model or None,
        )

        logger.info(f"Creating search provider: {provider_name}" + (f" model={search_model}" if search_model else ""))
        return cls.create(provider_name, **kwargs)
