import { useEffect, useRef, useState } from "react";
import { useChatSession, type WorkspaceSync } from "../hooks/useChatSession";
import { ArtifactPanel } from "./ArtifactPanel";
import { RuntimeModeControl } from "./RuntimeModeControl";
import { SessionSidebar } from "./SessionSidebar";
import { Button, EmptyState } from "./ui";

const CHIPS = [
  "只解读 JD",
  "调研公司",
  "快速匹配",
  "完整匹配报告",
  "深度 Gap 分析",
  "出学习计划",
  "生成本周周报",
];

function MessageBlock({ role, content }: { role: string; content: string }) {
  const isUser = role === "user";
  return (
    <div className="animate-fade-in border-b border-[rgba(55,53,47,0.06)] py-4 last:border-0">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-xs font-medium text-[#37352f]">{isUser ? "你" : "Copilot"}</span>
      </div>
      <div className="whitespace-pre-wrap text-sm leading-relaxed text-[#37352f]">{content}</div>
    </div>
  );
}

export function CopilotChat(
  sync: WorkspaceSync & { company?: string; onRuntimeChange?: () => void; onOpenGateway?: () => void }
) {
  const {
    session,
    sessions,
    messages,
    artifacts,
    pendingProposal,
    running,
    error,
    sendMessage,
    confirmProposal,
    createNewSession,
    switchSession,
    deleteSession,
    workspace,
  } = useChatSession(sync);
  const [input, setInput] = useState("");
  const [activeArt, setActiveArt] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const displayCompany = workspace?.company || sync.company;
  const pageTitle = session?.title && session.title !== "新对话" ? session.title : "Copilot";

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, running]);

  async function submit() {
    const t = input.trim();
    if (!t) return;
    setInput("");
    await sendMessage(t);
    if (artifacts.length) setActiveArt(artifacts[artifacts.length - 1]?.id ?? null);
  }

  return (
    <div className="flex h-full bg-white">
      <SessionSidebar
        sessions={sessions}
        activeId={session?.id ?? null}
        onSelect={(id) => void switchSession(id)}
        onCreate={() => void createNewSession()}
        onDelete={(id) => void deleteSession(id)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="shrink-0 border-b border-[rgba(55,53,47,0.09)] px-8 pt-8 pb-4">
          <div className="mx-auto flex max-w-2xl items-start justify-between gap-4">
            <div>
              <p className="mb-2 text-3xl">💬</p>
              <h1 className="text-2xl font-bold tracking-tight text-[#37352f]">{pageTitle}</h1>
              <p className="mt-1 text-sm text-[#787774]">
                {displayCompany
                  ? `当前关注 · ${String(displayCompany)}`
                  : "长期对话会保存在左侧列表，可随时切换"}
              </p>
            </div>
            <RuntimeModeControl onChange={sync.onRuntimeChange} onOpenGateway={sync.onOpenGateway} />
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-8 py-2">
          <div className="mx-auto max-w-2xl">
            {messages.length === 0 ? (
              <EmptyState
                icon="📋"
                title="开始写点什么"
                description="粘贴 JD 或简历。左侧可管理历史对话；右上角可切换 自动 / 离线 / 在线 模式。"
              />
            ) : (
              <div>
                {messages.map((m, i) => (
                  <MessageBlock key={i} role={m.role} content={m.content} />
                ))}
                {running ? (
                  <div className="py-4 text-sm text-[#9b9a97]">Copilot 正在思考…</div>
                ) : null}
              </div>
            )}
          </div>
        </div>

        <div className="shrink-0 border-t border-[rgba(55,53,47,0.09)] bg-[#fbfbfa] px-8 py-4">
          <div className="mx-auto max-w-2xl space-y-3">
            {pendingProposal ? (
              <div className="rounded-md border border-[rgba(35,131,226,0.3)] bg-[rgba(35,131,226,0.06)] px-4 py-3">
                <p className="text-xs font-medium text-[#2383e2]">待确认</p>
                <p className="mt-1 text-sm text-[#37352f]">
                  {String(pendingProposal.preview ?? "是否执行此操作？")}
                </p>
                <div className="mt-3 flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => confirmProposal(String(pendingProposal.id), "approve")}
                    disabled={running}
                  >
                    确认
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => confirmProposal(String(pendingProposal.id), "reject")}
                  >
                    取消
                  </Button>
                </div>
              </div>
            ) : null}

            <div className="flex flex-wrap gap-1.5">
              {CHIPS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => sendMessage(c)}
                  disabled={running}
                  className="rounded-md px-2 py-1 text-xs text-[#787774] hover:bg-[rgba(55,53,47,0.08)] hover:text-[#37352f] disabled:opacity-40"
                >
                  {c}
                </button>
              ))}
            </div>

            <div className="overflow-hidden rounded-md border border-[rgba(55,53,47,0.16)] bg-white shadow-[0_1px_2px_rgba(15,15,15,0.04)] focus-within:border-[#2383e2] focus-within:ring-2 focus-within:ring-[rgba(35,131,226,0.15)]">
              <textarea
                className="w-full resize-none bg-transparent px-3 py-3 text-sm text-[#37352f] placeholder-[#9b9a97] focus:outline-none"
                rows={3}
                placeholder="输入消息…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void submit();
                  }
                }}
              />
              <div className="flex items-center justify-between border-t border-[rgba(55,53,47,0.06)] px-3 py-2">
                <span className="text-[11px] text-[#9b9a97]">Enter 发送</span>
                <Button size="sm" onClick={() => void submit()} disabled={running || !input.trim()}>
                  {running ? "…" : "发送"}
                </Button>
              </div>
            </div>
            {error ? <p className="text-xs text-[#eb5757]">{error}</p> : null}
          </div>
        </div>
      </div>

      <div className="hidden w-72 shrink-0 flex-col border-l border-[rgba(55,53,47,0.09)] bg-[#f7f6f3] lg:flex">
        <div className="border-b border-[rgba(55,53,47,0.09)] px-4 py-3">
          <p className="text-sm font-medium text-[#37352f]">Artifacts</p>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <ArtifactPanel
            artifacts={artifacts}
            activeId={activeArt ?? artifacts[artifacts.length - 1]?.id ?? null}
            onSelect={setActiveArt}
          />
        </div>
      </div>
    </div>
  );
}
