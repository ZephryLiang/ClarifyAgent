import { useEffect, useState } from "react";
import { api } from "./api";
import type { Status } from "./types";
import { SAMPLE_JOB, SAMPLE_RESUME } from "./sampleData";
import { ResumeRewrite } from "./components/ResumeRewrite";
import { Matching } from "./components/Matching";
import { Outreach } from "./components/Outreach";
import { Interview } from "./components/Interview";
import { Retrospective } from "./components/Retrospective";
import { MemoryPanel } from "./components/MemoryPanel";
import { LlmGatewayPanel } from "./components/LlmGatewayPanel";
import { GovernancePanel } from "./components/GovernancePanel";
import { CopilotChat } from "./components/CopilotChat";
import { EvalsPanel } from "./components/EvalsPanel";
import { VersionBanner } from "./components/VersionBanner";
import { ProviderSwitcher } from "./components/ProviderSwitcher";
import { StatusDot } from "./components/ui";

type Tab = "copilot" | "rewrite" | "match" | "outreach" | "interview" | "retro" | "memory" | "llm" | "gov" | "evals";

type NavItem = { id: Tab; label: string; icon: string };

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "工作台",
    items: [{ id: "copilot", label: "Copilot", icon: "💬" }],
  },
  {
    label: "求职流程",
    items: [
      { id: "rewrite", label: "简历改写", icon: "✍️" },
      { id: "match", label: "建立匹配", icon: "🎯" },
      { id: "outreach", label: "打招呼", icon: "👋" },
      { id: "interview", label: "模拟面试", icon: "🎤" },
      { id: "retro", label: "面试复盘", icon: "🔍" },
    ],
  },
  {
    label: "系统",
    items: [
      { id: "memory", label: "记忆 & 日报", icon: "🧠" },
      { id: "llm", label: "LLM Gateway", icon: "⚡" },
      { id: "gov", label: "治理", icon: "🛡️" },
      { id: "evals", label: "评测", icon: "📊" },
    ],
  },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("copilot");
  const [status, setStatus] = useState<Status | null>(null);
  const [resume, setResume] = useState(SAMPLE_RESUME);
  const [job, setJob] = useState(SAMPLE_JOB);
  const [transcript, setTranscript] = useState("");
  const [company, setCompany] = useState("");

  useEffect(() => {
    api.getStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  function refreshStatus() {
    api.getStatus().then(setStatus).catch(() => setStatus(null));
  }

  const workspaceSync = {
    resume,
    job,
    company,
    transcript,
    onWorkspaceChange: (ws: {
      resume_text?: string;
      job_text?: string;
      company?: string;
      interview_transcript?: string;
    }) => {
      if (ws.resume_text !== undefined) setResume(ws.resume_text);
      if (ws.job_text !== undefined) setJob(ws.job_text);
      if (ws.company !== undefined) setCompany(ws.company);
      if (ws.interview_transcript !== undefined) setTranscript(ws.interview_transcript);
    },
  };

  const pageTitle =
    NAV_GROUPS.flatMap((g) => g.items).find((i) => i.id === tab)?.label ?? "Copilot";

  return (
    <div className="flex h-full min-h-screen bg-[#fbfbfa]">
      {/* Notion sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-[rgba(55,53,47,0.09)] bg-[#f7f6f3]">
        <div className="flex items-center gap-2 px-3 py-3">
          <span className="text-lg">🧭</span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-[#37352f]">求职 Agent</p>
            <p className="truncate text-[11px] text-[#9b9a97]">Job-seeking workspace</p>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-3">
              <p className="mb-1 px-2 text-[11px] font-medium text-[#9b9a97]">{group.label}</p>
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const active = tab === item.id;
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => setTab(item.id)}
                        className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors ${
                          active
                            ? "bg-[rgba(55,53,47,0.08)] font-medium text-[#37352f]"
                            : "text-[#787774] hover:bg-[rgba(55,53,47,0.06)]"
                        }`}
                      >
                        <span className="text-base leading-none opacity-80">{item.icon}</span>
                        <span className="truncate">{item.label}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-[rgba(55,53,47,0.09)] px-3 py-3 space-y-2">
          <ProviderSwitcher
            status={status}
            onChange={refreshStatus}
            onOpenGateway={() => setTab("llm")}
          />
          {status ? (
            <div className="flex items-center gap-2 text-xs text-[#787774]">
              <StatusDot ok={status.llm_enabled} />
              <span>
                {status.llm_mode === "offline"
                  ? "强制离线"
                  : status.llm_enabled
                    ? status.active_provider ?? "LLM 在线"
                    : status.llm_mode === "online"
                      ? "在线(未配置)"
                      : "自动·离线"}
              </span>
            </div>
          ) : (
            <span className="text-xs text-[#9b9a97]">连接中…</span>
          )}
        </div>
      </aside>

      {/* Main canvas */}
      <div className="flex min-w-0 flex-1 flex-col">
        <VersionBanner />

        {tab !== "copilot" ? (
          <header className="border-b border-[rgba(55,53,47,0.09)] bg-white px-10 py-6">
            <h1 className="text-3xl font-bold tracking-tight text-[#37352f]">{pageTitle}</h1>
            {company && tab === "retro" ? (
              <p className="mt-1 text-sm text-[#787774]">{company}</p>
            ) : null}
          </header>
        ) : null}

        <main className={`flex-1 overflow-hidden ${tab === "copilot" ? "" : "overflow-y-auto"}`}>
          {tab === "copilot" ? (
            <CopilotChat {...workspaceSync} onRuntimeChange={refreshStatus} onOpenGateway={() => setTab("llm")} />
          ) : (
            <div className="mx-auto max-w-3xl animate-fade-in px-10 py-8">
              {tab === "rewrite" && (
                <ResumeRewrite resume={resume} setResume={setResume} job={job} />
              )}
              {tab === "match" && (
                <Matching resume={resume} setResume={setResume} job={job} setJob={setJob} />
              )}
              {tab === "outreach" && <Outreach resume={resume} job={job} />}
              {tab === "interview" && (
                <Interview
                  resume={resume}
                  job={job}
                  onTranscript={(t) => {
                    setTranscript(t);
                    setTab("retro");
                  }}
                />
              )}
              {tab === "retro" && (
                <Retrospective
                  transcript={transcript}
                  setTranscript={setTranscript}
                  job={job}
                  company={company}
                  setCompany={setCompany}
                />
              )}
              {tab === "memory" && <MemoryPanel />}
              {tab === "llm" && <LlmGatewayPanel onChange={refreshStatus} />}
              {tab === "gov" && <GovernancePanel />}
              {tab === "evals" && <EvalsPanel />}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
