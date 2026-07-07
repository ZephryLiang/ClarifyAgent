import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ProviderCatalogItem, ProviderModelsResult, RuntimeSettings } from "../types";
import { Button, Card } from "./ui";
import { RuntimeModeControl } from "./RuntimeModeControl";

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  qwen: "通义千问",
  moonshot: "Moonshot",
  zhipu: "智谱",
  volcengine: "火山引擎",
};

const MODEL_FETCH_DEBOUNCE_MS = 600;

export function LlmGatewayPanel({ onChange }: { onChange?: () => void }) {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { api_key: string; model: string; base_url: string }>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, import("../types").ProviderTestResult>>({});
  const [modelOptions, setModelOptions] = useState<Record<string, string[]>>({});
  const [modelErrors, setModelErrors] = useState<Record<string, string>>({});
  const [loadingModels, setLoadingModels] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const modelFetchTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const draftsRef = useRef(drafts);
  draftsRef.current = drafts;

  const refresh = useCallback(async () => {
    const s = await api.getProviderSettings();
    setSettings(s);
    const d: Record<string, { api_key: string; model: string; base_url: string }> = {};
    for (const p of s.providers) {
      d[p.name] = { api_key: "", model: p.model, base_url: p.base_url || "" };
    }
    setDrafts(d);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  const loadModels = useCallback(
    async (name: string, draftOverride?: { api_key: string; model: string; base_url: string }) => {
      const p = settings?.providers.find((x) => x.name === name);
      if (!p || p.protocol !== "openai") return;
      const d = draftOverride ?? draftsRef.current[name];
      const hasDraftKey = Boolean(d?.api_key?.trim());
      if (!hasDraftKey && !p.configured) {
        setModelOptions((prev) => {
          const next = { ...prev };
          delete next[name];
          return next;
        });
        return;
      }

      setLoadingModels((prev) => ({ ...prev, [name]: true }));
      setModelErrors((prev) => {
        const next = { ...prev };
        delete next[name];
        return next;
      });
      try {
        const result: ProviderModelsResult = await api.listProviderModels(name, {
          api_key: d?.api_key?.trim() || undefined,
          base_url: d?.base_url?.trim() || undefined,
        });
        if (result.ok && result.models.length > 0) {
          setModelOptions((prev) => ({ ...prev, [name]: result.models }));
          setDrafts((prev) => {
            const cur = prev[name]?.model;
            const pick =
              cur && result.models.includes(cur)
                ? cur
                : result.models.find((m) => m.startsWith("ep-")) ?? result.models[0];
            return { ...prev, [name]: { ...prev[name], model: pick } };
          });
        } else {
          setModelOptions((prev) => {
            const next = { ...prev };
            delete next[name];
            return next;
          });
          if (result.error) {
            setModelErrors((prev) => ({ ...prev, [name]: result.error ?? "拉取失败" }));
          }
        }
      } catch (e) {
        setModelErrors((prev) => ({
          ...prev,
          [name]: e instanceof Error ? e.message : String(e),
        }));
      } finally {
        setLoadingModels((prev) => ({ ...prev, [name]: false }));
      }
    },
    [settings]
  );

  const scheduleModelFetch = useCallback(
    (name: string, draftOverride?: { api_key: string; model: string; base_url: string }) => {
      clearTimeout(modelFetchTimers.current[name]);
      modelFetchTimers.current[name] = setTimeout(() => {
        void loadModels(name, draftOverride);
      }, MODEL_FETCH_DEBOUNCE_MS);
    },
    [loadModels]
  );

  useEffect(() => {
    if (!settings) return;
    for (const p of settings.providers) {
      if (p.protocol === "openai" && p.configured) {
        void loadModels(p.name);
      }
    }
  }, [settings, loadModels]);

  useEffect(() => {
    return () => {
      for (const timer of Object.values(modelFetchTimers.current)) {
        clearTimeout(timer);
      }
    };
  }, []);

  async function testProvider(name: string) {
    setTesting(name);
    setMsg(null);
    try {
      const d = drafts[name];
      const result = await api.testProviderConnection(name, {
        api_key: d?.api_key || undefined,
        model: d?.model || undefined,
        base_url: d?.base_url || undefined,
        register: true,
        label: d?.model || undefined,
      });
      setTestResults((prev) => ({ ...prev, [name]: result }));
      if (result.ok) {
        const s = await api.getProviderSettings();
        setSettings(s);
        setDrafts((prev) => ({ ...prev, [name]: { ...prev[name], api_key: "" } }));
        onChange?.();
        setMsg(
          result.registered
            ? `${PROVIDER_LABELS[name] ?? name} 已注册 · ${result.latency_ms}ms`
            : `${PROVIDER_LABELS[name] ?? name} 连接成功 · ${result.latency_ms}ms`
        );
      } else {
        setMsg(`${PROVIDER_LABELS[name] ?? name} 连接失败：${result.error ?? "未知错误"}`);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(null);
    }
  }

  async function activateEntry(provider: string, entryId: string) {
    setBusy(provider);
    try {
      const s = await api.setActiveProviderEntry(provider, entryId);
      setSettings(s);
      onChange?.();
    } finally {
      setBusy(null);
    }
  }

  async function removeEntry(provider: string, entryId: string) {
    setBusy(provider);
    try {
      const s = await api.deleteProviderEntry(provider, entryId);
      setSettings(s);
      onChange?.();
    } finally {
      setBusy(null);
    }
  }

  async function movePriority(name: string, dir: number) {
    if (!settings) return;
    const prio = [...settings.provider_priority];
    const i = prio.indexOf(name);
    if (i < 0) return;
    const j = i + dir;
    if (j <= -1 || j >= prio.length) return;
    const tmp = prio[i];
    prio[i] = prio[j];
    prio[j] = tmp;
    const s = await api.setProviderPriority(prio);
    setSettings(s);
    onChange?.();
  }

  function updateDraft(
    name: string,
    patch: Partial<{ api_key: string; model: string; base_url: string }>
  ) {
    setDrafts((prev) => {
      const next = { ...prev, [name]: { ...prev[name], ...patch } };
      if (patch.api_key !== undefined || patch.base_url !== undefined) {
        scheduleModelFetch(name, next[name]);
      }
      return next;
    });
  }

  if (!settings) {
    return <p className="text-sm text-[#787774]">加载 Gateway 配置…</p>;
  }

  return (
    <div className="space-y-4">
      <Card title="运行模式">
        <p className="mb-3 text-xs text-[#787774]">
          双协议 LLM Gateway：OpenAI 兼容 + Anthropic 原生，按优先级自动 fallback。
          Key 可在此配置（存本地 SQLite），或写在 backend/.env。
        </p>
        <RuntimeModeControl onChange={() => { refresh(); onChange?.(); }} onOpenGateway={undefined} />
        {settings.active_provider ? (
          <p className="mt-2 text-xs text-[#2e7d32]">
            当前路由 · {settings.active_provider}
          </p>
        ) : (
          <p className="mt-2 text-xs text-[#b45309]">尚未配置可用 Provider</p>
        )}
      </Card>

      <Card title="Provider 优先级">
        <p className="mb-2 text-xs text-[#787774]">越靠上越优先；仅已配置 Key 的会参与路由。</p>
        <ul className="space-y-1">
          {settings.provider_priority.map((name, idx) => (
            <li
              key={name}
              className="flex items-center justify-between rounded-md bg-[rgba(55,53,47,0.04)] px-2 py-1.5 text-sm"
            >
              <span className="text-[#37352f]">
                {idx + 1}. {PROVIDER_LABELS[name] ?? name}
              </span>
              <span className="flex gap-1">
                <button type="button" className="text-xs text-[#787774] hover:text-[#37352f]" onClick={() => void movePriority(name, -1)}>↑</button>
                <button type="button" className="text-xs text-[#787774] hover:text-[#37352f]" onClick={() => void movePriority(name, 1)}>↓</button>
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Provider 配置">
        <p className="mb-4 text-xs text-[#787774]">
          每个 Provider 可注册多个 entry（测试连接成功后自动加入）。左下角可切换当前使用的 entry。
        </p>
      </Card>

      {settings.providers.map((p: ProviderCatalogItem) => (
        <Card key={p.name} title={PROVIDER_LABELS[p.name] ?? p.name}>
          <div className="mb-3 flex flex-wrap gap-2 text-xs">
            <span className="text-[#787774]">{p.protocol}</span>
            <span className="text-[#9b9a97]">{p.entry_count ?? 0} 个 entry</span>
            {loadingModels[p.name] ? <span className="text-[#2383e2]">拉取模型中…</span> : null}
          </div>

          {(p.entries ?? []).length > 0 ? (
            <ul className="mb-4 space-y-2">
              {(p.entries ?? []).map((ent) => {
                const isActive = settings.active_provider_entry?.entry_id === ent.id;
                return (
                  <li
                    key={ent.id}
                    className={`rounded-md border px-3 py-2 text-xs ${
                      isActive
                        ? "border-[rgba(35,131,226,0.35)] bg-[rgba(35,131,226,0.06)]"
                        : "border-[rgba(55,53,47,0.09)] bg-[rgba(55,53,47,0.02)]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-medium text-[#37352f] truncate">{ent.label}</p>
                        <p className="text-[#787774] truncate">{ent.model}</p>
                        <p className="text-[#9b9a97]">
                          {ent.api_key_masked}
                          {ent.latency_ms ? ` · ${ent.latency_ms}ms` : ""}
                          {isActive ? " · 当前使用" : ""}
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        {!isActive ? (
                          <button
                            type="button"
                            className="text-[#2383e2] hover:underline"
                            disabled={busy === p.name}
                            onClick={() => void activateEntry(p.name, ent.id)}
                          >
                            启用
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="text-[#eb5757] hover:underline"
                          disabled={busy === p.name}
                          onClick={() => void removeEntry(p.name, ent.id)}
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mb-3 text-xs text-[#9b9a97]">尚无已注册 entry，填写 Key 后点测试连接。</p>
          )}

          <p className="mb-2 text-[11px] font-medium text-[#787774]">添加新 entry</p>
          <div className="space-y-2">
            <input
              type="password"
              placeholder={p.configured ? "输入新 Key 覆盖…" : `API Key (${p.api_key_env})`}
              value={drafts[p.name]?.api_key ?? ""}
              onChange={(e) => updateDraft(p.name, { api_key: e.target.value })}
              className="w-full rounded-md border border-[rgba(55,53,47,0.16)] px-2 py-1.5 text-sm"
            />
            {modelOptions[p.name]?.length ? (
              <select
                value={drafts[p.name]?.model ?? ""}
                onChange={(e) => updateDraft(p.name, { model: e.target.value })}
                className="w-full rounded-md border border-[rgba(55,53,47,0.16)] bg-white px-2 py-1.5 text-sm"
              >
                {modelOptions[p.name].map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                placeholder={
                  p.name === "volcengine"
                    ? "Model 或推理接入点 ep-xxx（输入 Key 后自动拉取）"
                    : "Model（输入 Key 后自动拉取）"
                }
                value={drafts[p.name]?.model ?? p.model}
                onChange={(e) => updateDraft(p.name, { model: e.target.value })}
                className="w-full rounded-md border border-[rgba(55,53,47,0.16)] px-2 py-1.5 text-sm"
              />
            )}
            {modelOptions[p.name]?.length ? (
              <p className="text-[11px] text-[#787774]">
                已拉取 {modelOptions[p.name].length} 个模型
                {modelOptions[p.name].some((m) => m.startsWith("ep-"))
                  ? "（含推理接入点 ep-）"
                  : ""}
              </p>
            ) : null}
            {modelErrors[p.name] ? (
              <p className="text-[11px] text-[#b45309]">{modelErrors[p.name]}</p>
            ) : null}
            <input
              type="text"
              placeholder="Base URL（可选）"
              value={drafts[p.name]?.base_url ?? ""}
              onChange={(e) => updateDraft(p.name, { base_url: e.target.value })}
              className="w-full rounded-md border border-[rgba(55,53,47,0.16)] px-2 py-1.5 text-sm"
            />
            <div className="flex flex-wrap gap-2 pt-1">
              <Button
                size="sm"
                variant="primary"
                disabled={testing === p.name || busy === p.name}
                onClick={() => void testProvider(p.name)}
              >
                {testing === p.name ? "测试中…" : "测试并注册"}
              </Button>
              {p.protocol === "openai" ? (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={loadingModels[p.name] || busy === p.name}
                  onClick={() => void loadModels(p.name)}
                >
                  刷新模型
                </Button>
              ) : null}
            </div>
            {testResults[p.name] ? (
              <p
                className={`mt-2 text-xs ${
                  testResults[p.name].ok ? "text-[#2e7d32]" : "text-[#eb5757]"
                }`}
              >
                {testResults[p.name].ok
                  ? `✓ ${testResults[p.name].latency_ms}ms${testResults[p.name].registered ? " · 已注册" : ""}`
                  : `✗ ${testResults[p.name].error}`}
              </p>
            ) : null}
          </div>
        </Card>
      ))}

      {msg ? <p className="text-xs text-[#787774]">{msg}</p> : null}
    </div>
  );
}
