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

type Tab = "rewrite" | "match" | "outreach" | "interview" | "retro" | "memory";

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "rewrite", label: "简历改写", icon: "✍️" },
  { id: "match", label: "建立匹配", icon: "🎯" },
  { id: "outreach", label: "打招呼", icon: "👋" },
  { id: "interview", label: "模拟面试", icon: "🎤" },
  { id: "retro", label: "面试复盘", icon: "🔍" },
  { id: "memory", label: "记忆 & 日报", icon: "🧠" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("rewrite");
  const [status, setStatus] = useState<Status | null>(null);
  const [resume, setResume] = useState(SAMPLE_RESUME);
  const [job, setJob] = useState(SAMPLE_JOB);
  const [transcript, setTranscript] = useState("");
  const [company, setCompany] = useState("");

  useEffect(() => {
    api.getStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  return (
    <div className="min-h-full">
      <header className="border-b border-slate-800 bg-slate-900/60 px-6 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xl">🧭</span>
            <div>
              <h1 className="text-lg font-semibold text-white">求职 Agent</h1>
              <p className="text-xs text-slate-400">Agentic job-seeking assistant</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs">
            {status ? (
              <>
                <span className={`h-2 w-2 rounded-full ${status.llm_enabled ? "bg-emerald-400" : "bg-amber-400"}`} />
                <span className="text-slate-300">
                  {status.llm_enabled
                    ? `LLM: ${status.default_priority[0] ?? "on"}`
                    : "离线模式（未配置 LLM）"}
                </span>
                <span className="text-slate-500">· {status.tools.length} 工具</span>
              </>
            ) : (
              <span className="text-slate-500">连接中…</span>
            )}
          </div>
        </div>
      </header>

      <nav className="border-b border-slate-800 bg-slate-900/30 px-6">
        <div className="mx-auto flex max-w-6xl gap-1 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm transition ${
                tab === t.id
                  ? "border-indigo-500 text-white"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              <span className="mr-1.5">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="mx-auto max-w-6xl px-6 py-6">
        {tab === "rewrite" && <ResumeRewrite resume={resume} setResume={setResume} job={job} />}
        {tab === "match" && <Matching resume={resume} setResume={setResume} job={job} setJob={setJob} />}
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
      </main>

      <footer className="mx-auto max-w-6xl px-6 py-6 text-center text-xs text-slate-600">
        求职 Agent · 双协议 LLM Gateway · Agentic RAG · 可观测 Agent Harness
      </footer>
    </div>
  );
}
