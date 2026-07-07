import type { ChatSessionSummary } from "../types";

function formatTime(ts: number) {
  const d = new Date(ts * 1000);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) {
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
}

export function SessionSidebar({
  sessions,
  activeId,
  onSelect,
  onCreate,
  onDelete,
}: {
  sessions: ChatSessionSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex h-full w-52 shrink-0 flex-col border-r border-[rgba(55,53,47,0.09)] bg-[#f7f6f3]">
      <div className="flex items-center justify-between border-b border-[rgba(55,53,47,0.09)] px-3 py-2.5">
        <span className="text-xs font-medium text-[#787774]">对话</span>
        <button
          type="button"
          onClick={onCreate}
          className="rounded-md px-2 py-0.5 text-xs text-[#2383e2] hover:bg-[rgba(35,131,226,0.08)]"
        >
          + 新建
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {sessions.length === 0 ? (
          <p className="px-2 py-4 text-xs text-[#9b9a97]">暂无对话</p>
        ) : (
          <ul className="space-y-0.5">
            {sessions.map((s) => {
              const active = s.id === activeId;
              return (
                <li key={s.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelect(s.id)}
                    className={`w-full rounded-md px-2 py-2 text-left transition ${
                      active
                        ? "bg-[rgba(55,53,47,0.08)]"
                        : "hover:bg-[rgba(55,53,47,0.06)]"
                    }`}
                  >
                    <p className="truncate text-sm text-[#37352f]">{s.title}</p>
                    {s.preview ? (
                      <p className="mt-0.5 truncate text-[11px] text-[#9b9a97]">{s.preview}</p>
                    ) : null}
                    <p className="mt-1 text-[10px] text-[#c4c4c2]">
                      {formatTime(s.updated_at)}
                      {s.message_count ? ` · ${s.message_count} 条` : ""}
                    </p>
                  </button>
                  <button
                    type="button"
                    title="删除"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm(`删除「${s.title}」？`)) onDelete(s.id);
                    }}
                    className="absolute right-1 top-1 hidden rounded px-1 text-[10px] text-[#9b9a97] hover:bg-[rgba(235,87,87,0.1)] hover:text-[#eb5757] group-hover:block"
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
