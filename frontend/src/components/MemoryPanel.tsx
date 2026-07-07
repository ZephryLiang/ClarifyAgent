import { useEffect, useState } from "react";
import { api } from "../api";
import type { MemoryItem } from "../api";
import { Button, Card, Pill } from "./ui";

interface JournalData {
  markdown: string;
  stats: Record<string, number>;
  date: string;
}

const KINDS = ["insight", "principle", "preference", "fact", "recurring", "heuristic"];

const KIND_TONE: Record<string, string> = {
  insight: "indigo",
  principle: "green",
  preference: "amber",
  fact: "slate",
  recurring: "red",
  heuristic: "indigo",
};

export function MemoryPanel() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [content, setContent] = useState("");
  const [kind, setKind] = useState("insight");
  const [journal, setJournal] = useState<JournalData | null>(null);
  const [busy, setBusy] = useState(false);
  const [exportPath, setExportPath] = useState<string | null>(null);

  async function refresh() {
    const res = await api.listMemory();
    setMemories(res.memories);
  }
  useEffect(() => {
    refresh();
  }, []);

  async function add() {
    if (!content.trim()) return;
    await api.createMemory(content, kind, []);
    setContent("");
    refresh();
  }
  async function remove(id: string) {
    await api.deleteMemory(id);
    refresh();
  }
  async function genWeekJournal() {
    setBusy(true);
    try {
      const res = await api.journalWeek();
      setJournal({ markdown: res.result.markdown, stats: res.result.stats, date: res.result.date });
    } finally {
      setBusy(false);
    }
  }
  async function genJournal() {
    setBusy(true);
    try {
      const res = await api.journal();
      setJournal(res.result);
    } finally {
      setBusy(false);
    }
  }
  async function exportJournal() {
    const res = await api.journalExport();
    setExportPath(res.path);
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <Card title="记忆库（洞见 / 原则 / 偏好 / 反复出现）">
          <div className="mb-3 flex gap-2">
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-900/60 px-2 py-2 text-sm text-slate-100"
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>{k}</option>
              ))}
            </select>
            <input
              className="flex-1 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-100"
              placeholder="记一条值得长期记住的内容…"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
            />
            <Button onClick={add} disabled={!content.trim()}>记住</Button>
          </div>
          <p className="mb-3 text-xs text-slate-500">
            重复内容会自动合并并增强 salience（反复出现→越重要）。运行各模块后 Agent 也会自动反思沉淀洞见。
          </p>
          <div className="space-y-2 max-h-[55vh] overflow-y-auto">
            {memories.length === 0 ? (
              <p className="text-sm text-slate-500">暂无记忆。运行一次匹配/复盘后会自动沉淀。</p>
            ) : (
              memories.map((m) => (
                <div key={m.id} className="flex items-start gap-2 rounded-lg border border-slate-800 p-2">
                  <Pill tone={KIND_TONE[m.kind] ?? "slate"}>{m.kind}</Pill>
                  <div className="flex-1 text-sm text-slate-200">
                    {m.content}
                    {m.tags.length > 0 ? (
                      <span className="ml-2 text-xs text-slate-500">#{m.tags.join(" #")}</span>
                    ) : null}
                  </div>
                  {m.salience > 1 ? <span className="text-xs text-amber-400">×{m.salience}</span> : null}
                  <button className="text-xs text-slate-500 hover:text-red-400" onClick={() => remove(m.id)}>删</button>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <div className="space-y-4">
        <Card title="今日日报">
          <div className="flex gap-2">
            <Button onClick={genJournal} disabled={busy}>{busy ? "生成中…" : "生成今日日报"}</Button>
            <Button variant="ghost" onClick={genWeekJournal} disabled={busy}>本周周报</Button>
            <Button variant="ghost" onClick={exportJournal}>导出到 Obsidian</Button>
          </div>
          {exportPath ? <p className="mt-2 text-xs text-emerald-400">已导出: {exportPath}</p> : null}
          {journal ? (
            <div className="mt-3">
              <div className="mb-2 flex flex-wrap gap-1.5">
                {Object.entries(journal.stats).map(([k, v]) => (
                  <Pill key={k} tone="indigo">{k}: {v}</Pill>
                ))}
              </div>
              <pre className="max-h-[45vh] overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-200">
                {journal.markdown}
              </pre>
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">日报将汇总当天的匹配/改写/面试与沉淀的洞见。</p>
          )}
        </Card>
      </div>
    </div>
  );
}
