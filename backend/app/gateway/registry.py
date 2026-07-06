"""Provider registry with routing, fallback, and retries.

The registry is the single entry point the harness uses to talk to *some* LLM.
It hides which concrete provider answered and transparently fails over to the
next enabled provider (across protocols) when one errors out.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from ..config import ProviderConfig, Settings, settings as default_settings
from .anthropic_adapter import AnthropicAdapter
from .base import ChatProvider, ChatResponse, Message, ProviderError, ToolSpec
from .openai_adapter import OpenAIAdapter


def build_provider(cfg: ProviderConfig, timeout: float = 60.0) -> ChatProvider:
    if cfg.protocol == "anthropic":
        return AnthropicAdapter(cfg.name, cfg.model, cfg.api_key, cfg.base_url, timeout)
    return OpenAIAdapter(cfg.name, cfg.model, cfg.api_key, cfg.base_url, timeout)


class Gateway:
    """Multi-provider LLM gateway.

    Parameters
    ----------
    settings:
        Configuration to read the provider catalogue from.
    providers:
        Explicit provider list (used in tests to inject fakes). When given,
        the settings catalogue is ignored.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        providers: Optional[List[ChatProvider]] = None,
        max_retries: int = 2,
    ) -> None:
        self.settings = settings or default_settings
        self.max_retries = max_retries
        if providers is not None:
            self._providers = providers
        else:
            self._providers = [
                build_provider(cfg, self.settings.request_timeout)
                for cfg in self.settings.resolved_priority()
            ]

    @property
    def providers(self) -> List[ChatProvider]:
        return self._providers

    def available(self) -> bool:
        return any(p.available() for p in self._providers)

    def _ordered(self, prefer: Optional[str]) -> List[ChatProvider]:
        usable = [p for p in self._providers if p.available()]
        if prefer:
            usable.sort(key=lambda p: 0 if p.name == prefer else 1)
        return usable

    def chat(
        self,
        messages: List[Message],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        system: Optional[str] = None,
        prefer: Optional[str] = None,
        on_attempt: Optional[Callable[[str, Optional[Exception]], None]] = None,
    ) -> ChatResponse:
        """Call the first working provider, failing over on error.

        ``on_attempt(provider_name, error)`` is invoked after each attempt so
        the harness can record it in the trace (error is None on success).
        """

        candidates = self._ordered(prefer)
        if not candidates:
            raise ProviderError("no LLM provider is configured/available")

        last_error: Optional[Exception] = None
        for provider in candidates:
            for attempt in range(self.max_retries + 1):
                try:
                    resp = provider.chat(messages, tools, temperature, max_tokens, system)
                    if on_attempt:
                        on_attempt(provider.name, None)
                    return resp
                except ProviderError as exc:
                    last_error = exc
                    if on_attempt:
                        on_attempt(provider.name, exc)
                    # simple linear backoff before retrying the same provider
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (attempt + 1))
                    continue
        raise ProviderError(f"all providers failed; last error: {last_error}")

    def describe(self) -> List[dict]:
        return [
            {"name": p.name, "protocol": p.protocol, "model": p.model, "available": p.available()}
            for p in self._providers
        ]
