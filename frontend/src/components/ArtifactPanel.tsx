import type { Artifact } from "../types";
import { Card, EmptyState, Pill, ScoreBar } from "./ui";

const KIND_LABELS: Record<string, string> = {
  jd_analysis: "JD 解读",
  company_research: "公司调研",
  quick_score: "快速匹配",
  match_report: "匹配报告",
  gap_analysis: "Gap 分析",
  tech_research_digest: "技术调研",
  project_proposal: "项目建议",
  learning_plan: "学习计划",
  role_assessment: "岗位评估",
  job_market_report: "市场报告",
  journal: "日报/周报",
  mock_interview: "模拟面试",
  retrospective: "面试复盘",
};

function JDAnalysisCard({ data }: { data: Record<string, unknown> }) {
  return (
    <Card title="JD 解读">
      <p className="text-sm leading-relaxed text-[#37352f]">{String(data.summary ?? "")}</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {(data.hard_skills as string[] | undefined)?.map((s) => (
          <Pill key={s} tone="indigo">{s}</Pill>
        ))}
      </div>
    </Card>
  );
}

function LearningPlanCard({ data }: { data: Record<string, unknown> }) {
  const phases = (data.phases as { week: number; focus: string; hours: number }[]) ?? [];
  return (
    <Card title="学习计划">
      <p className="mb-3 text-xs text-[#787774]">{String(data.rationale ?? "")}</p>
      {phases.map((p) => (
        <div key={p.week} className="mb-2 border-l-2 border-[#2383e2] pl-3 text-sm">
          <span className="font-medium text-[#37352f]">Week {p.week}</span>
          <span className="text-[#787774]"> · {p.focus} ({p.hours}h)</span>
        </div>
      ))}
    </Card>
  );
}

function GapAnalysisCard({ data }: { data: Record<string, unknown> }) {
  const gaps = (data.gaps as { theme: string; severity: string; bridge: string }[]) ?? [];
  return (
    <Card title="Gap 分析">
      <ScoreBar label="匹配分" value={Number(data.score ?? 0)} />
      <ul className="mt-2 space-y-1.5 text-sm">
        {gaps.map((g) => (
          <li key={g.theme} className="flex flex-wrap items-center gap-1.5">
            <Pill tone={g.severity === "high" ? "red" : "amber"}>{g.theme}</Pill>
            <span className="text-[#787774]">{g.bridge}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function ArtifactPanel({
  artifacts,
  activeId,
  onSelect,
}: {
  artifacts: Artifact[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const active = artifacts.find((a) => a.id === activeId) ?? artifacts[artifacts.length - 1];

  if (!artifacts.length) {
    return (
      <EmptyState
        icon="📄"
        title="暂无内容"
        description="对话生成的报告会出现在这里，类似 Notion 侧边预览。"
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1">
        {artifacts.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => onSelect(a.id)}
            className={`rounded-md px-2 py-0.5 text-xs transition ${
              active?.id === a.id
                ? "bg-[rgba(55,53,47,0.08)] font-medium text-[#37352f]"
                : "text-[#787774] hover:bg-[rgba(55,53,47,0.06)]"
            }`}
          >
            {KIND_LABELS[a.kind] ?? a.kind}
          </button>
        ))}
      </div>
      {active ? <ArtifactRenderer artifact={active} /> : null}
    </div>
  );
}

function ArtifactRenderer({ artifact }: { artifact: Artifact }) {
  const d = artifact.data;
  switch (artifact.kind) {
    case "jd_analysis":
      return <JDAnalysisCard data={d} />;
    case "company_research":
      return (
        <Card title={`公司调研 · ${String(d.company ?? "")}`}>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-[#787774]">
            {String(d.findings ?? d.summary ?? "")}
          </pre>
        </Card>
      );
    case "quick_score":
    case "match_report": {
      const m = (d.match ?? d) as Record<string, unknown>;
      if (d.match || d.score !== undefined) {
        return (
          <Card title="匹配报告">
            <ScoreBar label="综合匹配" value={Number(m.score ?? 0)} />
            <p className="text-sm text-[#37352f]">{String(m.recommendation ?? d.synthesis ?? "")}</p>
          </Card>
        );
      }
      break;
    }
    case "learning_plan":
      return <LearningPlanCard data={d} />;
    case "gap_analysis":
      return <GapAnalysisCard data={d} />;
    case "journal":
      return (
        <Card title="日报 / 周报">
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-xs text-[#787774]">
            {String(d.markdown ?? "")}
          </pre>
        </Card>
      );
    default:
      return (
        <Card title={KIND_LABELS[artifact.kind] ?? artifact.kind}>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs text-[#787774]">
            {JSON.stringify(d, null, 2)}
          </pre>
        </Card>
      );
  }
  return null;
}
