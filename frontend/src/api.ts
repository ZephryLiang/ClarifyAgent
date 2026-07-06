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
};

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
