import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { RuntimeSettings } from "../types";

const MODE_LABELS: Record<string, string> = {
  auto: "自动",
  offline: "离线",
  online: "在线",
};

export function RuntimeModeControl({
  onChange,
  onOpenGateway,
}: {
  onChange?: () => void;
  onOpenGateway?: () => void;
}) {
  const [runtime, setRuntime] = useState<RuntimeSettings | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const r = await api.getRuntimeSettings();
    setRuntime(r);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  async function setMode(mode: string) {
    setBusy(true);
    try {
      const r = await api.setLlmMode(mode);
      setRuntime(r);
      onChange?.();
    } finally {
      setBusy(false);
    }
  }

  if (!runtime) return null;

  const modes = ["auto", "offline", "online"] as const;

  return (
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex items-center gap-2">
        <span className="text-xs text-[#9b9a97]">LLM</span>
        <div className="flex rounded-md border border-[rgba(55,53,47,0.16)] bg-white p-0.5">
          {modes.map((m) => (
            <button
              key={m}
              type="button"
              disabled={busy}
              onClick={() => void setMode(m)}
              className={`rounded px-2 py-0.5 text-xs transition ${
                runtime.llm_mode === m
                  ? "bg-[rgba(55,53,47,0.08)] font-medium text-[#37352f]"
                  : "text-[#787774] hover:text-[#37352f]"
              }`}
            >
              {MODE_LABELS[m]}
            </button>
          ))}
        </div>
      </div>
      {onOpenGateway ? (
        <button
          type="button"
          onClick={onOpenGateway}
          className="text-[11px] text-[#2383e2] hover:underline"
        >
          LLM Gateway · 配置 & 测试连接
        </button>
      ) : null}
      {!runtime.providers_configured && runtime.llm_mode !== "offline" ? (
        <span className="text-[10px] text-[#b45309]">未配置 Key</span>
      ) : null}
    </div>
  );
}
