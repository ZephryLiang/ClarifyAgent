import { useEffect, useState } from "react";
import { api } from "../api";
import type { Attribution, Replay, RunSummary } from "../api";
import { Card, Pill } from "./ui";

const MODULE_LABELS: Record<string, string> = {
  resume_rewrite: "简历改写",
  matching: "岗位匹配",
  outreach: "打招呼",
  retrospective: "面试复盘",
  journal: "日报",
};

export function EvalsPanel() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [attribution, setAttribution] = useState<Attribution | null>(null);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listRuns().then((r) => setRuns(r.runs));
  }, []);

  async function inspect(runId: string) {
    setSelected(runId);
    setReplay(null);
    setAttribution(await api.attribution(runId));
  }
  async function doReplay(runId: string) {
    setBusy(true);
    try {
      setReplay(await api.replay(runId));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card title="运行记录（点击查看归因/回放）">
        <div className="max-h-[70vh] space-y-1.5 overflow-y-auto">
          {runs.length === 0 ? (
            <p className="text-sm text-slate-500">暂无运行记录。先在其他标签跑一次任务。</p>
          ) : (
            runs.map((r) => (
              <div
                key={r.id}
                className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 text-sm ${
                  selected === r.id ? "border-indigo-500 bg-slate-800/60" : "border-slate-800"
                }`}
              >
                <Pill tone="indigo">{MODULE_LABELS[r.module] ?? r.module}</Pill>
                <span className="flex-1 text-xs text-slate-500">
                  {new Date(r.created_at * 1000).toLocaleString()}
                </span>
                <button className="text-xs text-indigo-400 hover:text-indigo-300" onClick={() => inspect(r.id)}>归因</button>
                <button className="text-xs text-emerald-400 hover:text-emerald-300" onClick={() => doReplay(r.id)} disabled={busy}>回放</button>
              </div>
            ))
          )}
        </div>
      </Card>

      <div className="space-y-4">
        {attribution ? (
          <Card title="O · 归因分析">
            <p className="mb-2 text-sm text-slate-200">{attribution.summary}</p>
            <div className="mb-2 flex flex-wrap gap-1.5">
              <Pill tone="slate">总耗时 {Math.round(attribution.total_duration_ms)}ms</Pill>
              <Pill tone="slate">总 token {attribution.total_tokens}</Pill>
            </div>
            <h4 className="mb-1 text-xs font-semibold text-slate-400">自耗时 Top</h4>
            {attribution.top_spans.map((s, i) => (
              <div key={i} className="flex justify-between text-xs text-slate-300">
                <span>{s.kind} · {s.name}</span>
                <span>{s.self_ms}ms</span>
              </div>
            ))}
            {attribution.root_cause ? (
              <p className="mt-2 text-sm text-red-400">
                失败根因（{attribution.root_cause.layer}）：{attribution.root_cause.name} — {attribution.root_cause.error}
              </p>
            ) : null}
          </Card>
        ) : null}

        {replay ? (
          <Card title="V · 轨迹回放对比">
            <div className="mb-2">
              <Pill tone={replay.trajectory_match ? "green" : "amber"}>
                {replay.trajectory_match ? "轨迹一致（可复现）" : "轨迹漂移"}
              </Pill>
            </div>
            <div className="text-xs text-slate-400">
              <div>原始轨迹: {replay.original_trajectory.join(" → ") || "（无工具调用）"}</div>
              <div>回放轨迹: {replay.replayed_trajectory.join(" → ") || "（无工具调用）"}</div>
            </div>
            <pre className="mt-2 overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/60 p-2 text-xs text-slate-300">
              {JSON.stringify(replay.diff, null, 2)}
            </pre>
          </Card>
        ) : null}

        {!attribution && !replay ? (
          <Card><p className="text-sm text-slate-500">选择一条运行记录查看归因或回放。</p></Card>
        ) : null}
      </div>
    </div>
  );
}
