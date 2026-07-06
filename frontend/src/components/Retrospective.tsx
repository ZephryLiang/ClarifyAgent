import { useStreamRun } from "../hooks";
import { Button, Card, TextArea } from "./ui";
import { TraceView } from "./TraceView";

interface RetroResult {
  overall: string;
  strengths: string[];
  weaknesses: string[];
  missed_points: string[];
  model_answers: { question: string; suggestion: string }[];
  improvement_plan: string[];
  references: string[];
  llm_used: boolean;
}

function List({ title, items }: { title: string; items: string[] }) {
  if (!items?.length) return null;
  return (
    <div className="mb-3">
      <h4 className="mb-1 text-sm font-semibold text-slate-300">{title}</h4>
      <ul className="list-disc pl-5 text-sm text-slate-300">
        {items.map((it, i) => <li key={i}>{it}</li>)}
      </ul>
    </div>
  );
}

export function Retrospective({
  transcript,
  setTranscript,
  job,
  company,
  setCompany,
}: {
  transcript: string;
  setTranscript: (v: string) => void;
  job: string;
  company: string;
  setCompany: (v: string) => void;
}) {
  const { spans, summary, result, running, error, run } = useStreamRun<RetroResult>();

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="面试记录">
          <TextArea rows={12} value={transcript} onChange={(e) => setTranscript(e.target.value)} placeholder="粘贴面试对话记录，或先在「模拟面试」完成一场面试自动带入…" />
          <input
            className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-900/60 p-2 text-sm text-slate-100"
            placeholder="目标公司（可选，用于搜索面经）"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
          <div className="mt-3">
            <Button onClick={() => run("/retrospective", { transcript, job_text: job, company })} disabled={running || !transcript.trim()}>
              {running ? "复盘中…" : "生成面试复盘"}
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
          <Card title="复盘报告">
            {result.overall ? <p className="mb-3 text-sm text-slate-200">{result.overall}</p> : null}
            <List title="✅ 优势" items={result.strengths} />
            <List title="⚠️ 不足" items={result.weaknesses} />
            <List title="🔍 遗漏要点" items={result.missed_points} />
            {result.model_answers?.length ? (
              <div className="mb-3">
                <h4 className="mb-1 text-sm font-semibold text-slate-300">💡 参考答案思路</h4>
                {result.model_answers.map((m, i) => (
                  <div key={i} className="mb-2 rounded-lg border border-slate-800 p-2">
                    <div className="text-xs text-slate-400">{m.question}</div>
                    <div className="text-sm text-slate-200">{m.suggestion}</div>
                  </div>
                ))}
              </div>
            ) : null}
            <List title="📈 提升计划" items={result.improvement_plan} />
            <List title="🔗 参考面经" items={result.references} />
          </Card>
        ) : (
          <Card><p className="text-sm text-slate-500">复盘报告将显示在这里。</p></Card>
        )}
      </div>
    </div>
  );
}
