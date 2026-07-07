import type { InterviewSession, Status, StreamEvent, TraceSummary } from "./types";

const BASE = "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function getStatus(): Promise<Status> {
  const res = await fetch(BASE + "/status");
  return res.json();
}

export interface RunResult<T> {
  run_id: string;
  result: T;
  trace: TraceSummary;
}

/**
 * POST an endpoint with `stream: true` and parse the Server-Sent Events.
 * Calls `onEvent` for every event; resolves with the final `result` event.
 */
export async function streamPost(
  path: string,
  body: unknown,
  onEvent: (e: StreamEvent) => void
): Promise<StreamEvent> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...(body as object), stream: true }),
  });
  if (!res.body) throw new Error("no response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: StreamEvent | null = null;

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      try {
        const event = JSON.parse(payload) as StreamEvent;
        onEvent(event);
        if (event.type === "result" || event.type === "error") final = event;
      } catch {
        /* ignore malformed chunk */
      }
    }
  }
  if (!final) throw new Error("stream ended without a result");
  if (final.type === "error") throw new Error(String(final.message));
  return final;
}

export const api = {
  getStatus,
  rewrite: (resume_text: string, job_text?: string) =>
    post<RunResult<unknown>>("/resume/rewrite", { resume_text, job_text }),
  match: (resume_text: string, job_text: string) =>
    post<RunResult<unknown>>("/match", { resume_text, job_text }),
  outreach: (resume_text: string, job_text: string, style: string) =>
    post<RunResult<unknown>>("/outreach", { resume_text, job_text, style }),
  interviewStart: (resume_text: string, job_text: string, language: string) =>
    post<{ session: InterviewSession; question: string; trace: TraceSummary }>(
      "/interview/start",
      { resume_text, job_text, language }
    ),
  interviewAnswer: (session_id: string, answer: string) =>
    post<{
      session: InterviewSession;
      question: string;
      finished: boolean;
      trace: TraceSummary;
    }>("/interview/answer", { session_id, answer }),
  retrospective: (payload: {
    transcript?: string;
    session_id?: string;
    job_text?: string;
    company?: string;
  }) => post<RunResult<unknown>>("/retrospective", payload),
  listMemory: async (kind?: string) => {
    const q = kind ? `?kind=${encodeURIComponent(kind)}` : "";
    const res = await fetch(BASE + "/memory" + q);
    return (await res.json()) as { memories: MemoryItem[] };
  },
  createMemory: (content: string, kind: string, tags: string[]) =>
    post<MemoryItem>("/memory", { content, kind, tags }),
  deleteMemory: async (id: string) => {
    await fetch(BASE + "/memory/" + id, { method: "DELETE" });
  },
  journal: () => post<RunResult<{ markdown: string; stats: Record<string, number>; date: string }>>("/journal", {}),
  journalExport: () => post<{ path: string; date: string }>("/journal/export", {}),
  audit: async () => {
    const res = await fetch(BASE + "/audit");
    return (await res.json()) as { entries: AuditEntry[] };
  },
  approvals: async () => {
    const res = await fetch(BASE + "/approvals");
    return (await res.json()) as { policy: string; approved_tools: string[] };
  },
  approveTool: (name: string) => post<{ ok: boolean; approved_tools: string[] }>("/approvals/" + encodeURIComponent(name), {}),
  revokeTool: async (name: string) => {
    const res = await fetch(BASE + "/approvals/" + encodeURIComponent(name), { method: "DELETE" });
    return (await res.json()) as { ok: boolean; approved_tools: string[] };
  },
  judge: (content: string, artifact_type: string) =>
    post<{ result: JudgeResult; trace: TraceSummary }>("/verify/judge", { content, artifact_type }),
  listRuns: async (limit = 30) => {
    const res = await fetch(BASE + "/runs?limit=" + limit);
    return (await res.json()) as { runs: RunSummary[] };
  },
  attribution: async (runId: string) => {
    const res = await fetch(BASE + `/runs/${runId}/attribution`);
    return (await res.json()) as Attribution;
  },
  replay: (runId: string) => post<Replay>(`/runs/${runId}/replay`, {}),
};

export interface RunSummary {
  id: string;
  module: string;
  created_at: number;
  trace_id: string;
}

export interface Attribution {
  trace_id: string;
  total_duration_ms: number;
  total_tokens: number;
  self_time_by_kind: Record<string, number>;
  tokens_by_provider: Record<string, number>;
  top_spans: { name: string; kind: string; self_ms: number; tokens: number }[];
  errors: { name: string; layer: string; error: string }[];
  root_cause: { name: string; layer: string; error: string } | null;
  summary: string;
}

export interface Replay {
  run_id: string;
  module: string;
  original_trajectory: string[];
  replayed_trajectory: string[];
  trajectory_match: boolean;
  diff: Record<string, unknown>;
}

export interface AuditEntry {
  id: string;
  ts: number;
  actor: string;
  tool: string;
  action: string;
  decision: string;
  args_summary: string;
}

export interface JudgeResult {
  score: number;
  passed: boolean;
  rationale: string;
  dimensions: { name: string; score: number; comment: string }[];
  llm_used: boolean;
}

export interface MemoryItem {
  id: string;
  kind: string;
  content: string;
  tags: string[];
  source: string;
  salience: number;
  created_at: number;
  updated_at: number;
}
