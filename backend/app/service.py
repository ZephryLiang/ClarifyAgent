"""Application service layer.

Wires together the gateway, tool registry (built-ins + MCP), storage, and the
feature modules into a single facade the API routes call. Construction is cheap
and dependency-injected so tests can build a service with fakes.
"""

from __future__ import annotations

from typing import Any

from .config import APP_VERSION, Settings
from .config import settings as default_settings
from .export import ObsidianExporter
from .gateway.registry import Gateway
from .governance import ApprovalManager
from .harness import StoreCheckpointer, ToolRegistry, Tracer
from .mcp import MCPManager
from .memory import MemoryManager
from .modules import (
    Matcher,
    MockInterviewer,
    OutreachWriter,
    ResumeRewriter,
    Retrospective,
)
from .modules.llm_config import (
    apply_stored_priority,
    reload_settings_with_store,
    test_provider_connection,
    list_provider_models,
)
from .modules.provider_registry import (
    apply_registry_to_settings,
    catalog_with_entries,
    delete_entry,
    load_registry,
    register_entry,
    set_active_entry,
)
from .modules.activity_ledger import ActivityLedger
from .modules.copilot import JobSeekerCopilot, create_session
from .modules.gap_analyzer import GapAnalyzer
from .modules.jd_analyzer import JDAnalyzer
from .modules.job_market import JobMarketAggregator
from .modules.learning_plan import LearningPlanGenerator
from .modules.project_advisor import ProjectAdvisor
from .modules.research_curator import ResearchCurator
from .modules.requirement_synth import RequirementSynthesizer
from .modules.role_assessor import RoleAssessor
from .modules.system_release import SystemReleaseLog
from .modules.tech_research import TechResearchAgent
from .modules.curator import MemoryCurator
from .modules.journal import JournalWriter
from .modules.verify import Judge
from .storage import Store
from .tools import build_registry
from .tools.memory import build_memory_tools


class AppServices:
    def __init__(self, settings: Settings | None = None,
                 gateway: Gateway | None = None,
                 store: Store | None = None) -> None:
        self.settings = settings or default_settings
        self.store = store or Store()
        self._apply_stored_provider_config()
        self.gateway = gateway or Gateway(self.settings)
        self.tools: ToolRegistry = build_registry()
        self.mcp = MCPManager.from_path(self.settings.mcp_config_path)

        # Long-term memory + agentic memory tools.
        self.memory = MemoryManager(self.store)
        for tool in build_memory_tools(self.memory):
            self.tools.register(tool)

        # Governance: HITL approval + audit for side-effecting tools.
        self.approver = ApprovalManager(self.store, self.settings.hitl_policy)
        # Durable execution: checkpointer for resumable agent runs.
        self.checkpointer = StoreCheckpointer(self.store)

        self.rewriter = ResumeRewriter(self.gateway, self.tools, approver=self.approver)
        self.matcher = Matcher(self.gateway, self.tools, approver=self.approver)
        self.outreach = OutreachWriter(self.gateway)
        self.interviewer = MockInterviewer(self.gateway)
        self.retrospective = Retrospective(self.gateway, self.tools, approver=self.approver)
        self.curator = MemoryCurator(self.memory, self.gateway)
        self.journal = JournalWriter(self.store, self.memory, self.gateway)
        self.judge = Judge(self.gateway)
        self.obsidian = ObsidianExporter()
        self._mcp_notes: list[str] = []

        # Copilot + extended modules
        self.activity = ActivityLedger(self.store)
        self.releases = SystemReleaseLog(self.store)
        self.releases.ensure_seeded()
        self.jd_analyzer = JDAnalyzer(self.gateway)
        self.gap_analyzer = GapAnalyzer(self.gateway)
        self.tech_research = TechResearchAgent(self.gateway, self.tools)
        self.project_advisor = ProjectAdvisor(self.gateway)
        self.research_curator = ResearchCurator(self.memory)
        self.requirement_synth = RequirementSynthesizer()
        self.learning_plan = LearningPlanGenerator()
        self.role_assessor = RoleAssessor(self.gateway)
        self.job_market = JobMarketAggregator()
        self.copilot = JobSeekerCopilot(self)
        self._load_runtime_settings()

    def _stored_keys(self) -> dict:
        raw = self.store.setting_get("provider_keys")
        return dict(raw) if isinstance(raw, dict) else {}

    def _load_registry(self) -> dict[str, Any]:
        raw = self.store.setting_get("provider_registry")
        reg = load_registry(raw, self._stored_keys())
        if raw != reg and reg.get("entries"):
            self.store.setting_set("provider_registry", reg)
        return reg

    def _save_registry(self, registry: dict[str, Any]) -> None:
        self.store.setting_set("provider_registry", registry)

    def _legacy_keys_from_registry(self, registry: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        active = registry.get("active")
        for pname, entries in (registry.get("entries") or {}).items():
            if not entries:
                continue
            ent = entries[0]
            if active and active.get("provider") == pname:
                for e in entries:
                    if e.get("id") == active.get("entry_id"):
                        ent = e
                        break
            out[pname] = {
                "api_key": ent.get("api_key"),
                "model": ent.get("model"),
                "base_url": ent.get("base_url"),
            }
        return out

    def _apply_stored_provider_config(self) -> None:
        registry = self._load_registry()
        prio = self.store.setting_get("provider_priority")
        legacy = self._legacy_keys_from_registry(registry)
        self.settings = reload_settings_with_store(legacy, prio)
        apply_registry_to_settings(self.settings, registry)
        apply_stored_priority(self.settings, prio)

    def rebuild_gateway(self) -> None:
        """Reload env + SQLite registry and refresh adapters without replacing Gateway."""
        mode = self.gateway.llm_mode
        registry = self._load_registry()
        prio = self.store.setting_get("provider_priority")
        legacy = self._legacy_keys_from_registry(registry)
        self.settings = reload_settings_with_store(legacy, prio)
        apply_registry_to_settings(self.settings, registry)
        apply_stored_priority(self.settings, prio)
        self.gateway.refresh(self.settings)
        self.gateway.set_llm_mode(mode)
        self._rewire_gateway_modules()

    def _rewire_gateway_modules(self) -> None:
        """Point feature modules at the shared gateway (same object, refreshed inside)."""
        gw = self.gateway
        self.rewriter.gateway = gw
        self.matcher.gateway = gw
        self.outreach.gateway = gw
        self.interviewer.gateway = gw
        self.retrospective.gateway = gw
        self.curator.gateway = gw
        self.journal.gateway = gw
        self.judge.gateway = gw
        self.jd_analyzer.gateway = gw
        self.gap_analyzer.gateway = gw
        self.tech_research.gateway = gw
        self.project_advisor.gateway = gw
        self.role_assessor.gateway = gw

    def provider_settings(self) -> dict[str, object]:
        registry = self._load_registry()
        catalog = catalog_with_entries(
            self.settings, registry, request_timeout=self.settings.request_timeout,
        )
        active = registry.get("active")
        active_provider = None
        active_entry = None
        if active:
            active_provider = active.get("provider")
            for p in catalog:
                if p["name"] == active_provider:
                    active_entry = next(
                        (e for e in p.get("entries", []) if e.get("id") == active.get("entry_id")),
                        None,
                    )
                    break
        return {
            "providers": catalog,
            "provider_priority": list(self.settings.provider_priority),
            "active_provider": self.gateway.active_provider_name(),
            "active_entry": active_entry,
            "active_provider_entry": active,
            **self.gateway.runtime_info(),
        }

    def set_provider_config(
        self,
        name: str,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        *,
        clear_key: bool = False,
    ) -> dict[str, object]:
        cfg = self.settings.get_provider(name)
        if cfg is None:
            raise ValueError(f"unknown provider: {name}")
        registry = self._load_registry()
        if clear_key:
            registry.setdefault("entries", {}).pop(name, None)
            if registry.get("active", {}).get("provider") == name:
                from .modules.provider_registry import pick_default_active
                registry["active"] = pick_default_active(registry)
            self._save_registry(registry)
            self.rebuild_gateway()
            return self.provider_settings()
        if api_key and api_key.strip():
            register_entry(
                registry,
                name,
                api_key=api_key.strip(),
                model=(model or cfg.model or "").strip(),
                base_url=(base_url if base_url is not None else cfg.base_url or "").strip(),
                label=(model or cfg.model or name).strip(),
            )
            self._save_registry(registry)
            self.rebuild_gateway()
        return self.provider_settings()

    def set_active_provider_entry(self, provider: str, entry_id: str) -> dict[str, object]:
        registry = self._load_registry()
        set_active_entry(registry, provider, entry_id)
        self._save_registry(registry)
        self.rebuild_gateway()
        return self.provider_settings()

    def delete_provider_entry(self, provider: str, entry_id: str) -> dict[str, object]:
        registry = self._load_registry()
        if not delete_entry(registry, provider, entry_id):
            raise ValueError(f"entry not found: {provider}/{entry_id}")
        self._save_registry(registry)
        self.rebuild_gateway()
        return self.provider_settings()

    def set_provider_priority(self, priority: list[str]) -> dict[str, object]:
        if not priority:
            raise ValueError("priority must not be empty")
        self.store.setting_set("provider_priority", priority)
        self.rebuild_gateway()
        return self.provider_settings()

    def test_provider(
        self,
        name: str,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        *,
        register: bool = True,
        label: str | None = None,
    ) -> dict[str, object]:
        legacy = self._legacy_keys_from_registry(self._load_registry())
        result = test_provider_connection(
            self.settings,
            name,
            legacy,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=self.settings.request_timeout,
        )
        if result.get("ok") and register and api_key and api_key.strip():
            registry = self._load_registry()
            cfg = self.settings.get_provider(name)
            ent = register_entry(
                registry,
                name,
                api_key=api_key.strip(),
                model=(model or result.get("model") or (cfg.model if cfg else "") or "").strip(),
                base_url=(base_url if base_url is not None else (cfg.base_url if cfg else "") or "").strip(),
                label=label or (model or result.get("model") or name),
                latency_ms=result.get("latency_ms"),
                set_active=True,
            )
            self._save_registry(registry)
            self.rebuild_gateway()
            result["entry_id"] = ent["id"]
            result["registered"] = True
        return result

    def list_provider_models(
        self,
        name: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, object]:
        legacy = self._legacy_keys_from_registry(self._load_registry())
        return list_provider_models(
            self.settings,
            name,
            legacy,
            api_key=api_key,
            base_url=base_url,
            timeout=self.settings.request_timeout,
        )

    def _load_runtime_settings(self) -> None:
        mode = self.store.setting_get("llm_mode")
        if isinstance(mode, str) and mode in ("auto", "offline", "online"):
            self.gateway.set_llm_mode(mode)

    def set_llm_mode(self, mode: str) -> dict[str, object]:
        self.gateway.set_llm_mode(mode)
        self.store.setting_set("llm_mode", mode)
        return self.runtime_settings()

    def runtime_settings(self) -> dict[str, object]:
        return self.provider_settings()

    async def reflect_after(self, module: str, input_data: dict[str, Any],
                            result: dict[str, Any], tracer: Tracer) -> None:
        """Best-effort post-run reflection to capture durable memories."""

        if module == "journal":
            return
        await self.curator.reflect(module, input_data, result, tracer)

    async def connect_mcp(self) -> list[str]:
        """Connect configured MCP servers and merge their tools into the registry."""

        self._mcp_notes = await self.mcp.connect()
        for tool in self.mcp.tools():
            self.tools.register(tool)
        return self._mcp_notes

    async def shutdown(self) -> None:
        await self.mcp.aclose()
        self.store.close()

    def status(self) -> dict:
        runtime = self.runtime_settings()
        active_entry = runtime.get("active_entry")
        label = None
        if active_entry:
            label = f"{runtime.get('active_provider_entry', {}).get('provider')}/{active_entry.get('label')}"
        return {
            "llm_enabled": runtime["llm_enabled"],
            "llm_mode": runtime["llm_mode"],
            "llm_effective_label": runtime["llm_effective_label"],
            "providers_configured": runtime["providers_configured"],
            "active_provider": runtime.get("active_provider"),
            "active_entry": active_entry,
            "active_provider_label": label,
            "providers": self.gateway.describe(),
            "provider_catalog": runtime.get("providers"),
            "provider_priority": runtime.get("provider_priority"),
            "tools": self.tools.names(),
            "mcp_notes": self._mcp_notes,
            "default_priority": [p.name for p in self.settings.resolved_priority()],
            "memory_count": len(self.memory.list()),
            "hitl_policy": self.approver.policy,
            "approved_tools": self.approver.approved_tools(),
            "app_version": APP_VERSION,
        }

    def new_tracer(self) -> Tracer:
        return Tracer()
