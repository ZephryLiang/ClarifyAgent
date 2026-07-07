import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Artifact, ChatSession, ChatSessionSummary, StreamEvent } from "../types";

const ACTIVE_SESSION_KEY = "clarify_active_session_id";

export interface WorkspaceSync {
  resume: string;
  job: string;
  company: string;
  transcript?: string;
  onWorkspaceChange?: (ws: {
    resume_text?: string;
    job_text?: string;
    company?: string;
    interview_transcript?: string;
  }) => void;
}

function loadSessionState(s: ChatSession) {
  return {
    messages: s.messages?.map((m) => ({ role: m.role, content: m.content })) ?? [],
    artifacts: s.artifacts ?? [],
    pending: s.pending_proposal ?? null,
  };
}

export function useChatSession(sync?: WorkspaceSync) {
  const [session, setSession] = useState<ChatSession | null>(null);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [pendingProposal, setPendingProposal] = useState<Record<string, unknown> | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initRef = useRef(false);

  const refreshSessionList = useCallback(async () => {
    const list = await api.listChatSessions(50);
    setSessions(list);
  }, []);

  const applySession = useCallback((s: ChatSession) => {
    const st = loadSessionState(s);
    setSession(s);
    setMessages(st.messages);
    setArtifacts(st.artifacts);
    setPendingProposal(st.pending);
    localStorage.setItem(ACTIVE_SESSION_KEY, s.id);
    if (s.workspace && sync?.onWorkspaceChange) {
      sync.onWorkspaceChange({
        resume_text: s.workspace.resume_text as string | undefined,
        job_text: s.workspace.job_text as string | undefined,
        company: s.workspace.company as string | undefined,
        interview_transcript: s.workspace.interview_transcript as string | undefined,
      });
    }
  }, [sync]);

  const loadSession = useCallback(async (id: string) => {
    const s = await api.getChatSession(id);
    applySession(s);
  }, [applySession]);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    (async () => {
      try {
        await refreshSessionList();
        const savedId = localStorage.getItem(ACTIVE_SESSION_KEY);
        if (savedId) {
          try {
            await loadSession(savedId);
            return;
          } catch {
            localStorage.removeItem(ACTIVE_SESSION_KEY);
          }
        }
        const res = await api.createChatSession({
          resume_text: sync?.resume ?? "",
          job_text: sync?.job ?? "",
          company: sync?.company ?? "",
        });
        applySession(res.session);
        await refreshSessionList();
      } catch (e) {
        setError(String(e));
      }
    })();
  }, [applySession, loadSession, refreshSessionList, sync?.company, sync?.job, sync?.resume]);

  const syncSession = useCallback((s: ChatSession) => {
    applySession(s);
    void refreshSessionList();
  }, [applySession, refreshSessionList]);

  const createNewSession = useCallback(async () => {
    const res = await api.createChatSession({
      resume_text: sync?.resume ?? "",
      job_text: sync?.job ?? "",
      company: sync?.company ?? "",
    });
    applySession(res.session);
    await refreshSessionList();
  }, [applySession, refreshSessionList, sync?.company, sync?.job, sync?.resume]);

  const switchSession = useCallback(async (id: string) => {
    if (id === session?.id) return;
    setError(null);
    await loadSession(id);
  }, [loadSession, session?.id]);

  const deleteSession = useCallback(async (id: string) => {
    await api.deleteChatSession(id);
    await refreshSessionList();
    if (session?.id === id) {
      const list = await api.listChatSessions(50);
      if (list.length > 0) {
        await loadSession(list[0].id);
      } else {
        await createNewSession();
      }
    }
  }, [createNewSession, loadSession, refreshSessionList, session?.id]);

  const renameSession = useCallback(async (id: string, title: string) => {
    const s = await api.updateChatSession(id, { title });
    if (session?.id === id) applySession(s);
    await refreshSessionList();
  }, [applySession, refreshSessionList, session?.id]);

  const sendMessage = useCallback(async (text: string) => {
    if (!session?.id || !text.trim()) return;
    setRunning(true);
    setError(null);
    setMessages((m) => [...m, { role: "user", content: text }]);
    try {
      const updated = await api.streamChatMessage(session.id, text, (e: StreamEvent) => {
        if (e.type === "artifact" && e.artifact) {
          setArtifacts((a) => {
            const exists = a.find((x) => x.id === e.artifact!.id);
            if (exists) return a.map((x) => (x.id === e.artifact!.id ? e.artifact! : x));
            return [...a, e.artifact!];
          });
        }
        if (e.type === "proposal" && e.proposal) {
          setPendingProposal(e.proposal as Record<string, unknown>);
        }
      });
      if (updated.session) syncSession(updated.session);
      if (updated.message) {
        setMessages((m) => [...m, { role: "assistant", content: updated.message! }]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, [session?.id, syncSession]);

  const confirmProposal = useCallback(async (proposalId: string, action: "approve" | "reject" = "approve") => {
    if (!session?.id) return;
    setRunning(true);
    setError(null);
    try {
      const updated = await api.confirmChatProposal(session.id, proposalId, action, (e: StreamEvent) => {
        if (e.type === "artifact" && e.artifact) {
          setArtifacts((a) => [...a.filter((x) => x.id !== e.artifact!.id), e.artifact!]);
        }
        if (e.type === "proposal") setPendingProposal(null);
      });
      if (updated.session) syncSession(updated.session);
      if (updated.message) {
        setMessages((m) => [...m, { role: "assistant", content: updated.message! }]);
      }
      if (action === "reject") setPendingProposal(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }, [session?.id, syncSession]);

  return {
    session,
    sessions,
    messages,
    artifacts,
    pendingProposal,
    running,
    error,
    sendMessage,
    confirmProposal,
    createNewSession,
    switchSession,
    deleteSession,
    renameSession,
    refreshSessionList,
    workspace: session?.workspace,
  };
}
