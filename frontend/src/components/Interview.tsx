import { useState } from "react";
import { api } from "../api";
import type { InterviewSession } from "../types";
import { Button, Card, Pill, TextArea } from "./ui";

export function Interview({
  resume,
  job,
  onTranscript,
}: {
  resume: string;
  job: string;
  onTranscript: (t: string, sessionId: string) => void;
}) {
  const [session, setSession] = useState<InterviewSession | null>(null);
  const [language, setLanguage] = useState("zh");
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.interviewStart(resume, job, language);
      setSession(res.session);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!session || !answer.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.interviewAnswer(session.id, answer);
      setSession(res.session);
      setAnswer("");
      if (res.finished) {
        const transcript = res.session.turns
          .map((t) => `${t.role === "interviewer" ? "面试官" : "候选人"}: ${t.content}`)
          .join("\n");
        onTranscript(transcript, res.session.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      {!session ? (
        <Card title="开始模拟面试">
          <div className="mb-3 flex items-center gap-2 text-sm">
            <span className="text-slate-400">语言:</span>
            {["zh", "en"].map((l) => (
              <button
                key={l}
                onClick={() => setLanguage(l)}
                className={`rounded px-3 py-1 ${language === l ? "bg-indigo-600 text-white" : "bg-slate-700/60 text-slate-300"}`}
              >
                {l === "zh" ? "中文" : "English"}
              </button>
            ))}
          </div>
          <Button onClick={start} disabled={busy || !resume.trim() || !job.trim()}>
            {busy ? "准备中…" : "开始面试"}
          </Button>
          <p className="mt-2 text-xs text-slate-500">面试官会基于岗位 JD 与你的简历逐轮提问并追问。</p>
        </Card>
      ) : (
        <>
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <Pill tone="indigo">
                第 {session.question_count} / {session.max_questions} 问
              </Pill>
              {session.finished ? <Pill tone="green">面试结束</Pill> : null}
            </div>
            <div className="max-h-[50vh] space-y-3 overflow-y-auto">
              {session.turns.map((t, i) => (
                <div key={i} className={`flex ${t.role === "candidate" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${t.role === "candidate" ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-100"}`}>
                    {t.content}
                  </div>
                </div>
              ))}
            </div>
          </Card>
          {!session.finished ? (
            <Card>
              <TextArea rows={3} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="输入你的回答…" />
              <div className="mt-2 flex gap-2">
                <Button onClick={send} disabled={busy || !answer.trim()}>{busy ? "思考中…" : "提交回答"}</Button>
                <Button variant="ghost" onClick={() => setSession(null)}>结束</Button>
              </div>
            </Card>
          ) : (
            <Card>
              <p className="text-sm text-slate-300">面试已结束，去「面试复盘」标签查看分析（记录已带入）。</p>
            </Card>
          )}
          {error ? <p className="text-sm text-red-400">{error}</p> : null}
        </>
      )}
      {error && !session ? <p className="text-sm text-red-400">{error}</p> : null}
    </div>
  );
}
