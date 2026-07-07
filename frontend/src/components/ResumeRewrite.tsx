import { useStreamRun } from "../hooks";
import type { RewriteSuggestion } from "../types";
import { Button, Card, Pill, TextArea } from "./ui";
import { TraceView } from "./TraceView";

interface RewriteResult {
  suggestions: RewriteSuggestion[];
  llm_used: boolean;
  summary: string;
}

export function ResumeRewrite({
  resume,
  setResume,
  job,
}: {
  resume: string;
  setResume: (v: string) => void;
  job: string;
}) {
  const { spans, summary, result, running, error, run } = useStreamRun<RewriteResult>();

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="简历（原文）">
          <TextArea
            rows={14}
            value={resume}
            onChange={(e) => setResume(e.target.value)}
            placeholder="粘贴你的简历文本…"
          />
          <div className="mt-3">
            <Button onClick={() => run("/resume/rewrite", { resume_text: resume, job_text: job })} disabled={running || !resume.trim()}>
              {running ? "改写中…" : "有依据地改写简历"}
            </Button>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            改写严格基于知识库最佳实践（XYZ/STAR/量化/强动词），绝不虚构；缺数据处会用占位符提示补充。
          </p>
        </Card>
        <Card title="Agent 执行轨迹">
          <TraceView spans={spans} summary={summary} />
        </Card>
      </div>

      <div className="space-y-4">
        {error ? <Card><p className="text-red-400 text-sm">{error}</p></Card> : null}
        {result ? (
          <Card title={`改写建议（${result.suggestions.length}）`}>
            <div className="mb-3">
              <Pill tone={result.llm_used ? "indigo" : "slate"}>
                {result.llm_used ? "LLM 生成" : "离线规则引擎"}
              </Pill>
            </div>
            <div className="space-y-4">
              {result.suggestions.map((s, i) => (
                <div key={i} className="rounded-lg border border-slate-800 p-3">
                  <div className="text-xs text-slate-500 line-through">{s.original}</div>
                  <div className="mt-1 text-sm text-slate-100">{s.rewritten}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {s.principles.map((p, j) => (
                      <Pill key={j} tone="amber">依据 {p}</Pill>
                    ))}
                    {s.faithfulness && !s.faithfulness.ok ? (
                      <Pill tone="red">⚠ 疑似幻觉: {s.faithfulness.issues.map((x) => x.value).join(", ")}</Pill>
                    ) : (
                      <Pill tone="green">✓ 忠实度校验通过</Pill>
                    )}
                  </div>
                  {s.needs_input.length > 0 ? (
                    <ul className="mt-2 list-disc pl-5 text-xs text-slate-400">
                      {s.needs_input.map((n, k) => <li key={k}>{n}</li>)}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>
        ) : (
          <Card><p className="text-sm text-slate-500">改写结果将显示在这里。</p></Card>
        )}
      </div>
    </div>
  );
}
