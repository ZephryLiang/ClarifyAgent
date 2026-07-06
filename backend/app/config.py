"""Runtime configuration for the 求职 Agent backend.

Everything is driven by environment variables so the app runs the same way
locally, in CI, and in a container. Nothing here *requires* a key — the app
degrades gracefully to offline behaviour when no provider is configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Repository / package paths.
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
KNOWLEDGE_BASE_DIR = Path(
    os.getenv("JOBSEEKER_KB_DIR", str(BACKEND_DIR / "knowledge_base"))
)
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = Path(os.getenv("JOBSEEKER_DB", str(BACKEND_DIR / "jobseeker.db")))


@dataclass
class ProviderConfig:
    """A single LLM provider entry in the gateway registry."""

    name: str
    protocol: str  # "openai" | "anthropic"
    model: str
    api_key_env: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # resolved at load time

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


# Built-in provider catalogue. Each entry is enabled automatically when its
# API-key environment variable is present. base_url values point at the public
# OpenAI-compatible / Anthropic endpoints; override via env if you use a gateway.
_DEFAULT_PROVIDERS: List[ProviderConfig] = [
    ProviderConfig("openai", "openai", os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                   "OPENAI_API_KEY", os.getenv("OPENAI_BASE_URL")),
    ProviderConfig("anthropic", "anthropic", os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
                   "ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_BASE_URL")),
    ProviderConfig("deepseek", "openai", os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                   "DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")),
    ProviderConfig("qwen", "openai", os.getenv("QWEN_MODEL", "qwen-plus"),
                   "DASHSCOPE_API_KEY",
                   os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
    ProviderConfig("moonshot", "openai", os.getenv("MOONSHOT_MODEL", "moonshot-v1-8k"),
                   "MOONSHOT_API_KEY", os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")),
    ProviderConfig("zhipu", "openai", os.getenv("ZHIPU_MODEL", "glm-4-flash"),
                   "ZHIPU_API_KEY", os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")),
]


@dataclass
class Settings:
    providers: List[ProviderConfig] = field(default_factory=list)
    # Ordered preference for routing; first enabled provider wins by default.
    provider_priority: List[str] = field(default_factory=lambda: _priority_list())
    default_provider: Optional[str] = field(default=os.getenv("JOBSEEKER_PROVIDER"))
    max_tool_iterations: int = int(os.getenv("JOBSEEKER_MAX_ITERATIONS", "8"))
    request_timeout: float = float(os.getenv("JOBSEEKER_TIMEOUT", "60"))
    mcp_config_path: Optional[str] = os.getenv("JOBSEEKER_MCP_CONFIG")

    def enabled_providers(self) -> List[ProviderConfig]:
        return [p for p in self.providers if p.enabled]

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        for p in self.providers:
            if p.name == name:
                return p
        return None

    def resolved_priority(self) -> List[ProviderConfig]:
        """Enabled providers ordered by preference then catalogue order."""

        order: Dict[str, int] = {n: i for i, n in enumerate(self.provider_priority)}
        enabled = self.enabled_providers()
        return sorted(enabled, key=lambda p: order.get(p.name, 999))


def _priority_list() -> List[str]:
    raw = os.getenv("JOBSEEKER_PROVIDER_PRIORITY")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return ["anthropic", "openai", "deepseek", "qwen", "moonshot", "zhipu"]


def load_settings() -> Settings:
    providers: List[ProviderConfig] = []
    for p in _DEFAULT_PROVIDERS:
        p.api_key = os.getenv(p.api_key_env)
        providers.append(p)
    return Settings(providers=providers)


# A module-level singleton is convenient; call reload_settings() in tests.
settings = load_settings()


def reload_settings() -> Settings:
    global settings
    settings = load_settings()
    return settings
