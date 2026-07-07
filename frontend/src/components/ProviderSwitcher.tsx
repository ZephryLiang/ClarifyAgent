import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { ProviderCatalogItem, ProviderEntry, Status } from "../types";

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  qwen: "通义千问",
  moonshot: "Moonshot",
  zhipu: "智谱",
  volcengine: "火山引擎",
};

export function ProviderSwitcher({
  status,
  onChange,
  onOpenGateway,
}: {
  status: Status | null;
  onChange?: () => void;
  onOpenGateway?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<ProviderCatalogItem[]>([]);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const s = await api.getProviderSettings();
    setSettings(s.providers);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh, status?.active_provider]);

  const active = status?.active_entry;
  const activeProvider = status?.active_provider;

  async function selectEntry(provider: string, entry: ProviderEntry) {
    setBusy(true);
    try {
      await api.setActiveProviderEntry(provider, entry.id);
      onChange?.();
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  const allEntries = settings.flatMap((p) =>
    (p.entries ?? []).map((e) => ({ provider: p.name, entry: e }))
  );

  return (
    <div className="relative">
      <button
        type="button"
        disabled={busy}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-xs text-[#37352f] hover:bg-[rgba(55,53,47,0.06)]"
      >
        <span className="min-w-0 truncate">
          {active
            ? `${PROVIDER_LABELS[activeProvider ?? ""] ?? activeProvider} · ${active.label}`
            : "选择 LLM Provider"}
        </span>
        <span className="text-[#9b9a97]">{open ? "▴" : "▾"}</span>
      </button>

      {open ? (
        <div className="absolute bottom-full left-0 right-0 z-20 mb-1 max-h-56 overflow-y-auto rounded-md border border-[rgba(55,53,47,0.12)] bg-white py-1 shadow-lg">
          {allEntries.length === 0 ? (
            <p className="px-3 py-2 text-[11px] text-[#787774]">暂无已注册 Provider</p>
          ) : (
            settings.map((p) =>
              (p.entries ?? []).length > 0 ? (
                <div key={p.name} className="px-2 py-1">
                  <p className="px-1 text-[10px] font-medium text-[#9b9a97]">
                    {PROVIDER_LABELS[p.name] ?? p.name}
                  </p>
                  {(p.entries ?? []).map((e) => {
                    const isActive =
                      activeProvider === p.name && active?.id === e.id;
                    return (
                      <button
                        key={e.id}
                        type="button"
                        disabled={busy}
                        onClick={() => void selectEntry(p.name, e)}
                        className={`mt-0.5 flex w-full flex-col rounded px-2 py-1.5 text-left text-[11px] ${
                          isActive
                            ? "bg-[rgba(35,131,226,0.1)] text-[#2383e2]"
                            : "text-[#37352f] hover:bg-[rgba(55,53,47,0.06)]"
                        }`}
                      >
                        <span className="font-medium truncate">{e.label}</span>
                        <span className="truncate text-[#9b9a97]">{e.model}</span>
                      </button>
                    );
                  })}
                </div>
              ) : null
            )
          )}
          {onOpenGateway ? (
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onOpenGateway();
              }}
              className="mt-1 w-full border-t border-[rgba(55,53,47,0.08)] px-3 py-2 text-left text-[11px] text-[#2383e2] hover:bg-[rgba(55,53,47,0.04)]"
            >
              管理 LLM Gateway…
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
