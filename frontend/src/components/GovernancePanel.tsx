import { useEffect, useState } from "react";
import { api } from "../api";
import type { AuditEntry, JudgeResult } from "../api";
import { Button, Card, Pill, ScoreBar, TextArea } from "./ui";

export function GovernancePanel() {
  const [policy, setPolicy] = useState("");
  const [approved, setApproved] = useState<string[]>([]);
  const [toolName, setToolName] = useState("");
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [content, setContent] = useState("将 QPS 从 2k 提升到 15k，P99 下降 40%。");
  const [judgeResult, setJudgeResult] = useState<JudgeResult | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const a = await api.approvals();
    setPolicy(a.policy);
    setApproved(a.approved_tools);
    setAudit((await api.audit()).entries);
  }
  useEffect(() => {
    refresh();
  }, []);

  async function approve() {
    if (!toolName.trim()) return;
    await api.approveTool(toolName.trim());
    setToolName("");
    refresh();
  }
  async function revoke(name: string) {
    await api.revokeTool(name);
    refresh();
  }
  async function runJudge() {
    setBusy(true);
    try {
      const res = await api.judge(content, "简历/文本");
      setJudgeResult(res.result);
    } finally {
      setBusy(false);
    }
  }

  const decisionTone: Record<string, string> = {
    human_approved: "green",
    auto_approved: "green",
    blocked_pending_approval: "amber",
    denied: "red",
    revoked: "slate",
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="治理 · HITL 审批">
          <div className="mb-3 flex items-center gap-2 text-sm">
            <span className="text-slate-400">当前策略:</span>
            <Pill tone={policy === "auto" ? "amber" : policy === "deny" ? "red" : "indigo"}>{policy}</Pill>
            <span className="text-xs text-slate-500">(confirm=副作用操作需人工批准)</span>
          </div>
          <div className="mb-3 flex gap-2">
            <input
              className="flex-1 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100"
              placeholder="工具名，如 boss-agent__greet"
              value={toolName}
              onChange={(e) => setToolName(e.target.value)}
            />
            <Button onClick={approve} disabled={!toolName.trim()}>批准</Button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {approved.length === 0 ? (
              <span className="text-sm text-slate-500">暂无已批准的副作用工具。</span>
            ) : (
              approved.map((t) => (
                <button key={t} onClick={() => revoke(t)} className="group">
                  <Pill tone="green">{t} ✕</Pill>
                </button>
              ))
            )}
          </div>
        </Card>

        <Card title="审计日志">
          <div className="max-h-[40vh] space-y-1.5 overflow-y-auto">
            {audit.length === 0 ? (
              <p className="text-sm text-slate-500">暂无审计记录。</p>
            ) : (
              audit.map((e) => (
                <div key={e.id} className="flex items-center gap-2 rounded bg-slate-800/40 px-2 py-1.5 text-xs">
                  <span className="text-slate-500">{new Date(e.ts * 1000).toLocaleTimeString()}</span>
                  <Pill tone={decisionTone[e.decision] ?? "slate"}>{e.decision}</Pill>
                  <span className="text-slate-300">{e.action}</span>
                  {e.tool ? <span className="text-slate-400">{e.tool}</span> : null}
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <div className="space-y-4">
        <Card title="校验 · LLM-as-judge">
          <TextArea rows={6} value={content} onChange={(e) => setContent(e.target.value)} placeholder="粘贴要评审的文本（简历条目/求职信/回答）…" />
          <div className="mt-3">
            <Button onClick={runJudge} disabled={busy || !content.trim()}>{busy ? "评审中…" : "评审打分"}</Button>
          </div>
          {judgeResult ? (
            <div className="mt-4">
              <div className="mb-2 flex items-center gap-2">
                <Pill tone={judgeResult.passed ? "green" : "red"}>{judgeResult.passed ? "通过" : "待改进"}</Pill>
                <Pill tone={judgeResult.llm_used ? "indigo" : "slate"}>{judgeResult.llm_used ? "LLM 评审" : "离线启发式"}</Pill>
              </div>
              <ScoreBar label="综合得分" value={judgeResult.score} />
              {judgeResult.rationale ? <p className="mb-2 text-sm text-slate-300">{judgeResult.rationale}</p> : null}
              {judgeResult.dimensions.map((d, i) => (
                <div key={i} className="mb-1">
                  <ScoreBar label={d.name} value={d.score} />
                  {d.comment ? <p className="text-xs text-slate-500">{d.comment}</p> : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">评审结果将显示在这里。</p>
          )}
        </Card>
      </div>
    </div>
  );
}
