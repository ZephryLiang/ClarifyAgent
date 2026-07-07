import { useEffect, useState } from "react";
import { api } from "../api";

const STORAGE_KEY = "clarify_last_seen_version";

export function VersionBanner() {
  const [info, setInfo] = useState<{ version: string; headline?: string } | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    api.getMetaVersion().then((v) => {
      const last = localStorage.getItem(STORAGE_KEY);
      if (last !== v.version) {
        setInfo({ version: v.version, headline: v.headline ?? v.title });
      }
    }).catch(() => {});
  }, []);

  if (!info || dismissed) return null;

  function dismiss() {
    if (info) localStorage.setItem(STORAGE_KEY, info.version);
    setDismissed(true);
  }

  return (
    <div className="border-b border-[rgba(35,131,226,0.2)] bg-[rgba(35,131,226,0.06)] px-4 py-2">
      <div className="flex items-center justify-between gap-4 text-xs text-[#37352f]">
        <p>
          <span className="font-medium text-[#2383e2]">v{info.version}</span>
          {" · "}
          {info.headline ?? "Copilot 已上线"}
        </p>
        <button
          type="button"
          onClick={dismiss}
          className="rounded-md px-2 py-0.5 text-[#787774] hover:bg-[rgba(55,53,47,0.08)]"
        >
          关闭
        </button>
      </div>
    </div>
  );
}
