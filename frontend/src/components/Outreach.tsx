import { useState } from "react";
import { useStreamRun } from "../hooks";
import { Button, Card, Pill } from "./ui";
import { TraceView } from "./TraceView";

interface OutreachResult {
  message: string;
  variants: string[];
  llm_used: boolean;
}

const STYLES = [
  { id: "professional", label: "专业稳重" },
  { id: "warm", label: "亲切热情" },
  { id: "concise", label: "简洁直接" },
];

export function Outreach({ resume, job }: { resume: string; job: string }) {
  const [style, setStyle] = useState("professional");
  const { spans, summary, result, running, error, run } = useStreamRun<OutreachResult>();

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="打招呼风格">
          <div className="flex gap-2">
            {STYLES.map((s) => (
              <button
                key={s.id}
                onClick={() => setStyle(s.id)}
                className={`rounded-lg px-3 py-1.5 text-sm ${style === s.id ? "bg-indigo-600 text-white" : "bg-slate-700/60 text-slate-300"}`}
              >
                {s.label}
              </button>
            ))}
          </div>
          <div className="mt-4">
            <Button onClick={() => run("/outreach", { resume_text: resume, job_text: job, style })} disabled={running || !resume.trim() || !job.trim()}>
              {running ? "生成中…" : "生成打招呼消息"}
            </Button>
          </div>
        </Card>
        <Card title="Agent 执行轨迹">
          <TraceView spans={spans} summary={summary} />
        </Card>
      </div>
      <div className="space-y-4">
        {error ? <Card><p className="text-red-400 text-sm">{error}</p></Card> : null}
        {result ? (
          <Card title="打招呼消息">
            <div className="mb-3"><Pill tone={result.llm_used ? "indigo" : "slate"}>{result.llm_used ? "LLM 生成" : "离线模板"}</Pill></div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-100 whitespace-pre-wrap">
              {result.message}
            </div>
            <button
              className="mt-3 text-xs text-indigo-400 hover:text-indigo-300"
              onClick={() => navigator.clipboard?.writeText(result.message)}
            >
              复制
            </button>
          </Card>
        ) : (
          <Card><p className="text-sm text-slate-500">打招呼消息将显示在这里。</p></Card>
        )}
      </div>
    </div>
  );
}
