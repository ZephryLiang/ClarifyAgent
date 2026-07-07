import type { Span, TraceSummary } from "../types";

const KIND_COLOR: Record<string, string> = {
  agent: "bg-indigo-500",
  subagent: "bg-violet-500",
  llm: "bg-emerald-500",
  tool: "bg-amber-500",
  mcp: "bg-sky-500",
  retrieval: "bg-pink-500",
};

const STATUS_DOT: Record<string, string> = {
  running: "bg-yellow-400 animate-pulse",
  ok: "bg-emerald-400",
  error: "bg-red-500",
};

function depthOf(span: Span, byId: Map<string, Span>): number {
  let depth = 0;
  let cur: Span | undefined = span;
  const seen = new Set<string>();
  while (cur && cur.parent_id && !seen.has(cur.id)) {
    seen.add(cur.id);
    cur = byId.get(cur.parent_id);
    depth += 1;
    if (depth > 8) break;
  }
  return depth;
}

export function TraceView({
  spans,
  summary,
}: {
  spans: Span[];
  summary?: TraceSummary | null;
}) {
  if (spans.length === 0) {
    return (
      <div className="text-slate-500 text-sm p-4">
        Agent 执行轨迹将在这里实时显示（LLM 调用 / 工具 / 子 agent）。
      </div>
    );
  }
  const byId = new Map(spans.map((s) => [s.id, s]));

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-4 text-xs text-slate-400 mb-2">
        <span>span: {summary?.span_count ?? spans.length}</span>
        {summary?.total_tokens ? <span>tokens: {summary.total_tokens}</span> : null}
        {summary?.duration_ms ? <span>耗时: {Math.round(summary.duration_ms)}ms</span> : null}
      </div>
      {spans.map((s) => {
        const depth = depthOf(s, byId);
        return (
          <div
            key={s.id}
            className="flex items-center gap-2 rounded-md bg-slate-800/40 px-2 py-1.5 text-sm"
            style={{ marginLeft: depth * 16 }}
          >
            <span className={`h-2 w-2 rounded-full ${STATUS_DOT[s.status] ?? "bg-slate-500"}`} />
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium text-white ${KIND_COLOR[s.kind] ?? "bg-slate-600"}`}>
              {s.kind}
            </span>
            <span className="text-slate-200 truncate flex-1">{s.name}</span>
            {s.attributes?.provider ? (
              <span className="text-[10px] text-slate-400">{String(s.attributes.provider)}</span>
            ) : null}
            {s.tokens ? <span className="text-[10px] text-slate-500">{s.tokens}tok</span> : null}
            <span className="text-[10px] text-slate-500 w-14 text-right">
              {s.duration_ms != null ? `${Math.round(s.duration_ms)}ms` : "…"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
