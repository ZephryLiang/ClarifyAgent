import { useStreamRun } from "../hooks";
import type { MatchResult } from "../types";
import { Button, Card, Pill, ScoreBar, TextArea } from "./ui";
import { TraceView } from "./TraceView";

interface MatchReport {
  match: MatchResult | null;
  analyses: Record<string, string>;
  synthesis: string;
  llm_used: boolean;
}

export function Matching({
  resume,
  setResume,
  job,
  setJob,
}: {
  resume: string;
  setResume: (v: string) => void;
  job: string;
  setJob: (v: string) => void;
}) {
  const { spans, summary, result, running, error, run } = useStreamRun<MatchReport>();
  const m = result?.match;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="简历">
          <TextArea rows={8} value={resume} onChange={(e) => setResume(e.target.value)} />
        </Card>
        <Card title="岗位 JD">
          <TextArea rows={8} value={job} onChange={(e) => setJob(e.target.value)} />
        </Card>
        <Button onClick={() => run("/match", { resume_text: resume, job_text: job })} disabled={running || !resume.trim() || !job.trim()}>
          {running ? "分析中…" : "建立匹配（并行子 agent）"}
        </Button>
        <Card title="Agent 执行轨迹">
          <TraceView spans={spans} summary={summary} />
        </Card>
      </div>

      <div className="space-y-4">
        {error ? <Card><p className="text-red-400 text-sm">{error}</p></Card> : null}
        {m ? (
          <>
            <Card title="匹配度">
              <ScoreBar label="综合匹配" value={m.score} />
              <ScoreBar label="技能匹配" value={m.skill_score} />
              <ScoreBar label="经验匹配" value={m.experience_score} />
              <div className="mt-2"><Pill tone="indigo">{m.verdict}</Pill></div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {m.matched_skills.map((s) => <Pill key={s} tone="green">{s}</Pill>)}
                {m.missing_required.map((s) => <Pill key={s} tone="red">缺 {s}</Pill>)}
                {m.missing_preferred.map((s) => <Pill key={s} tone="amber">加分 {s}</Pill>)}
              </div>
            </Card>
            {result?.synthesis ? (
              <Card title="综合建议">
                <p className="whitespace-pre-wrap text-sm text-slate-200">{result.synthesis}</p>
              </Card>
            ) : null}
            {result && Object.keys(result.analyses).length > 0 ? (
              <Card title="子 agent 分析">
                {Object.entries(result.analyses).map(([k, v]) => (
                  <details key={k} className="mb-2">
                    <summary className="cursor-pointer text-sm text-indigo-300">{k}</summary>
                    <p className="mt-1 whitespace-pre-wrap text-xs text-slate-300">{v}</p>
                  </details>
                ))}
              </Card>
            ) : null}
          </>
        ) : (
          <Card><p className="text-sm text-slate-500">匹配报告将显示在这里。</p></Card>
        )}
      </div>
    </div>
  );
}
