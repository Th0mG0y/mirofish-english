"""
Multi-provider LLM abstraction layer
Supports OpenAI and Anthropic providers with unified interface
"""

import json
import re
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from ..config import Config
from .openai_compatible import is_local_base_url, resolve_openai_compatible_api_key
from ..utils.logger import get_logger

logger = get_logger('mirofish.llm_provider')


def _clean_json_text(content: str) -> str:
    cleaned = (content or "").strip()
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    return cleaned.strip()


def _dedupe_citations(citations: List["Citation"]) -> List["Citation"]:
    seen = set()
    deduped = []
    for citation in citations:
        key = ((citation.url or "").strip().lower(), (citation.title or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped


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
            fallback=Config.LLM_API_KEY or Config.get_openai_cli_api_key(),
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
                                        snippet=(
                                            getattr(ann, 'text', '')
                                            or getattr(ann, 'quote', '')
                                            or getattr(ann, 'excerpt', '')
                                        )
                                    ))

            return WebSearchResult(query=query, answer=answer, citations=_dedupe_citations(citations))

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
        self._delegate: Optional[LLMProvider] = None

        if Config.use_claude_cli_for_anthropic():
            if api_key:
                logger.info("CLAUDE_CLI_USE_CREDENTIALS is enabled; ignoring explicit Anthropic API key and using Claude CLI instead")
            self._delegate = ClaudeCliProvider(model=model or Config.ANTHROPIC_MODEL_NAME)
            self.api_key = ""
            self.model = self._delegate.model
            return

        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError("anthropic package is required. Install with: pip install anthropic>=0.40.0")

        explicit_api_key = api_key or Config.ANTHROPIC_API_KEY
        cli_token = None if explicit_api_key else Config.get_claude_cli_api_key()
        self.api_key = explicit_api_key or cli_token
        self.model = model or Config.ANTHROPIC_MODEL_NAME

        if cli_token and Config.is_claude_cli_oauth_token(cli_token) and not explicit_api_key:
            raise ValueError(
                "Claude CLI OAuth access tokens are not supported by Anthropic API requests. "
                "Set ANTHROPIC_API_KEY to use the Anthropic provider."
            )

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
        if self._delegate is not None:
            return self._delegate.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                response_format=response_format,
            )

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
        if self._delegate is not None:
            return self._delegate.supports_web_search()
        return True

    def web_search(
        self,
        query: str,
        context: str = "",
        user_location: Optional[Dict] = None
    ) -> WebSearchResult:
        if self._delegate is not None:
            return self._delegate.web_search(
                query=query,
                context=context,
                user_location=user_location,
            )

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

            return WebSearchResult(query=query, answer=answer, citations=_dedupe_citations(citations))

        except Exception as e:
            logger.warning(f"Anthropic web search failed: {e}")
            return WebSearchResult(query=query, answer=f"Search failed: {str(e)}", citations=[])


class ClaudeCliProvider(LLMProvider):
    """Claude Code-backed provider for Anthropic workloads"""

    def __init__(
        self,
        model: Optional[str] = None,
        command: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        permission_mode: Optional[str] = None,
    ):
        self.model = model or Config.ANTHROPIC_MODEL_NAME
        self.command = command or Config.CLAUDE_CLI_COMMAND or "claude"
        self.timeout_seconds = timeout_seconds or Config.CLAUDE_CLI_TIMEOUT_SECONDS
        self.permission_mode = permission_mode or Config.CLAUDE_CLI_PERMISSION_MODE or "plan"

        if not shutil.which(self.command):
            raise ValueError(
                f"Claude CLI command '{self.command}' was not found on PATH. "
                "Set CLAUDE_CLI_COMMAND or install Claude Code."
            )

        self._verify_auth()
        logger.info(f"ClaudeCliProvider initialized: model={self.model}, command={self.command}")

    def _verify_auth(self) -> None:
        result = subprocess.run(
            [self.command, "auth", "status", "--text"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=min(self.timeout_seconds, 20),
            check=False,
        )
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "").strip()
            raise ValueError(
                "Claude CLI is not authenticated. Run `claude auth login` first."
                + (f" Details: {error_text}" if error_text else "")
            )

    def _split_messages(self, messages: List[Dict[str, str]]) -> tuple[str, List[Dict[str, str]]]:
        system_parts: List[str] = []
        conversation_messages: List[Dict[str, str]] = []

        for msg in messages:
            role = (msg.get("role") or "").strip().lower()
            content = msg.get("content") or ""
            if role == "system":
                system_parts.append(content)
            elif role in {"user", "assistant"}:
                conversation_messages.append({"role": role, "content": content})

        return "\n\n".join(part for part in system_parts if part), conversation_messages

    def _render_conversation(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return ""

        if len(messages) == 1 and messages[0].get("role") == "user":
            return messages[0].get("content", "").strip()

        if all(message.get("role") == "user" for message in messages):
            return "\n\n".join(
                message.get("content", "").strip()
                for message in messages
                if message.get("content", "").strip()
            )

        lines = [
            "Continue the conversation transcript below.",
            "Return only the assistant's next reply to the final user message.",
            "",
            "Transcript:",
        ]

        for msg in messages:
            role = msg.get("role", "user").strip().upper()
            lines.append(f"{role}:")
            lines.append(msg.get("content", "").strip())
            lines.append("")

        lines.append("ASSISTANT:")
        return "\n".join(lines)

    def _run_cli(
        self,
        prompt: str,
        system_prompt: str = "",
        json_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        command = [
            self.command,
            "-p",
            "--output-format",
            "json",
            "--no-session-persistence",
        ]

        if self.model:
            command.extend(["--model", self.model])
        if self.permission_mode:
            command.extend(["--permission-mode", self.permission_mode])
        if json_schema:
            command.extend(["--json-schema", json.dumps(json_schema, ensure_ascii=False)])

        system_prompt_path = None
        if system_prompt.strip():
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
                handle.write(system_prompt)
                system_prompt_path = handle.name
            command.extend(["--system-prompt-file", system_prompt_path])

        prompt_instruction = (
            "Use the piped input as the full task and return only the requested structured output."
            if json_schema
            else "Use the piped input as the full task and return only the assistant reply."
        )
        command.append(prompt_instruction)

        try:
            result = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        finally:
            if system_prompt_path:
                try:
                    import os
                    os.unlink(system_prompt_path)
                except OSError:
                    pass

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()

        if result.returncode != 0:
            raise RuntimeError(stderr or stdout or "Claude CLI invocation failed")
        if not stdout:
            raise RuntimeError("Claude CLI returned no output")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Claude CLI returned invalid JSON: {stdout}") from exc

        if payload.get("is_error"):
            raise RuntimeError(payload.get("result") or stderr or "Claude CLI reported an error")

        return payload

    def _usage_from_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, int]]:
        usage = payload.get("usage") or {}
        prompt_tokens = int(usage.get("input_tokens", 0) or 0)
        completion_tokens = int(usage.get("output_tokens", 0) or 0)

        if not prompt_tokens and not completion_tokens:
            return None

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
        response_format: Optional[Dict] = None
    ) -> ProviderResponse:
        system_prompt, conversation_messages = self._split_messages(messages)
        json_schema = None
        if response_format and response_format.get("type") == "json_schema":
            json_schema = response_format.get("schema")
        elif response_format and response_format.get("type") == "json_object":
            json_instruction = (
                "You must respond with valid JSON only. "
                "Do not include any text, explanation, or markdown formatting outside the JSON object."
            )
            system_prompt = f"{system_prompt}\n\n{json_instruction}".strip() if system_prompt else json_instruction

        payload = self._run_cli(
            prompt=self._render_conversation(conversation_messages),
            system_prompt=system_prompt,
            json_schema=json_schema,
        )

        content = payload.get("result", "")
        if response_format and response_format.get("type") == "json_schema":
            content = json.dumps(payload.get("structured_output") or {}, ensure_ascii=False)
        elif response_format and response_format.get("type") == "json_object":
            content = _clean_json_text(content)

        return ProviderResponse(
            content=content.strip(),
            model=self.model,
            usage=self._usage_from_payload(payload),
        )

    def supports_web_search(self) -> bool:
        return True

    def web_search(
        self,
        query: str,
        context: str = "",
        user_location: Optional[Dict] = None
    ) -> WebSearchResult:
        prompt_sections = [
            "Search the web for directly relevant evidence and answer the question.",
            "",
            f"Question: {query}",
        ]

        if context:
            prompt_sections.extend([
                "",
                "Context:",
                context,
            ])

        if user_location:
            prompt_sections.extend([
                "",
                "User location hint:",
                json.dumps(user_location, ensure_ascii=False),
            ])

        prompt_sections.extend([
            "",
            "Use live web search when helpful.",
            "Return concise citations with url, title, and snippet only for sources you actually used.",
        ])

        payload = self._run_cli(
            prompt="\n".join(prompt_sections),
            system_prompt="You are a careful research assistant. Ground your answer in current external evidence.",
            json_schema={
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "title": {"type": "string"},
                                "snippet": {"type": "string"},
                            },
                            "required": ["url", "title", "snippet"],
                        },
                    },
                },
                "required": ["answer", "citations"],
            },
        )

        structured_output = payload.get("structured_output") or {}
        citations = [
            Citation(
                url=item.get("url", ""),
                title=item.get("title", ""),
                snippet=item.get("snippet", ""),
            )
            for item in structured_output.get("citations", []) or []
        ]
        return WebSearchResult(
            query=query,
            answer=(structured_output.get("answer") or "").strip(),
            citations=_dedupe_citations(citations),
        )


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

            return WebSearchResult(query=query, answer=answer, citations=_dedupe_citations(citations))

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
