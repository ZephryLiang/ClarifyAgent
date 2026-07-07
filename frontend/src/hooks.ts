import { useCallback, useState } from "react";
import { streamPost } from "./api";
import type { Span, StreamEvent, TraceSummary } from "./types";

/** Manage a streaming agent run: live spans + final result. */
export function useStreamRun<T>() {
  const [spans, setSpans] = useState<Span[]>([]);
  const [summary, setSummary] = useState<TraceSummary | null>(null);
  const [result, setResult] = useState<T | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (path: string, body: unknown) => {
    setRunning(true);
    setError(null);
    setResult(null);
    setSpans([]);
    setSummary(null);
    const live = new Map<string, Span>();
    try {
      const final = await streamPost(path, body, (e: StreamEvent) => {
        if ((e.type === "span_start" || e.type === "span_end") && e.span) {
          live.set(e.span.id, e.span);
          setSpans(Array.from(live.values()));
        }
      });
      setResult(final.result as T);
      if (final.trace) {
        setSummary(final.trace);
        setSpans(final.trace.spans);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, []);

  return { spans, summary, result, running, error, run };
}
