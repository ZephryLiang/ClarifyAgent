"""FastAPI application: REST endpoints + SSE streaming of agent traces."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .harness import Tracer
from .observability import analyze_trace
from .schemas import (
    ChatConfirmRequest,
    ChatMessageRequest,
    ChatSessionCreateRequest,
    ChatSessionUpdateRequest,
    RuntimeSettingsRequest,
    ProviderConfigRequest,
    ProviderPriorityRequest,
    ProviderTestRequest,
    SetActiveProviderEntryRequest,
    ExportRequest,
    InterviewAnswerRequest,
    InterviewStartRequest,
    JudgeRequest,
    JournalRequest,
    MatchRequest,
    MemoryCreateRequest,
    MemoryUpdateRequest,
    OutreachRequest,
    RetrospectiveRequest,
    RewriteRequest,
)
from .modules.copilot import create_session
from .service import AppServices

app = FastAPI(title="求职 Agent", version="0.1.0",
              description="Agentic job-seeking assistant")

services: AppServices = AppServices()

app.add_middleware(
    CORSMiddleware,
    allow_origins=services.settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    await services.connect_mcp()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await services.shutdown()


# --------------------------------------------------------------------------- #
# SSE helper
# --------------------------------------------------------------------------- #

def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _stream_run(
    module: str,
    input_data: dict[str, Any],
    runner: Callable[[Tracer], Awaitable[Any]],
) -> StreamingResponse:
    """Run ``runner`` while streaming its trace events, then emit the result."""

    tracer = services.new_tracer()

    async def watch() -> Any:
        try:
            result = await runner(tracer)
            result_dict = result.to_dict() if hasattr(result, "to_dict") else result
            await services.reflect_after(module, input_data, result_dict, tracer)
            return result_dict
        finally:
            tracer.close()

    async def gen():
        watcher = asyncio.create_task(watch())
        try:
            async for event in tracer.events():
                yield _sse(event)
            result_dict = await watcher
            run_id = services.store.save_run(module, input_data, result_dict, tracer.summary())
            yield _sse({"type": "result", "run_id": run_id,
                        "result": result_dict, "trace": tracer.summary()})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _run_json(module: str, input_data: dict[str, Any],
                    runner: Callable[[Tracer], Awaitable[Any]]) -> dict[str, Any]:
    tracer = services.new_tracer()
    result = await runner(tracer)
    result_dict = result.to_dict() if hasattr(result, "to_dict") else result
    await services.reflect_after(module, input_data, result_dict, tracer)
    run_id = services.store.save_run(module, input_data, result_dict, tracer.summary())
    return {"run_id": run_id, "result": result_dict, "trace": tracer.summary()}


# --------------------------------------------------------------------------- #
# Meta endpoints
# --------------------------------------------------------------------------- #

@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def status() -> dict[str, Any]:
    return services.status()


@app.get("/api/settings/runtime")
async def get_runtime_settings() -> dict[str, Any]:
    return services.runtime_settings()


@app.put("/api/settings/runtime")
async def set_runtime_settings(req: RuntimeSettingsRequest) -> dict[str, Any]:
    try:
        return services.set_llm_mode(req.llm_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings/providers")
async def get_provider_settings() -> dict[str, Any]:
    return services.provider_settings()


@app.put("/api/settings/providers/{provider_name}")
async def set_provider_settings(provider_name: str, req: ProviderConfigRequest) -> dict[str, Any]:
    try:
        return services.set_provider_config(
            provider_name,
            api_key=req.api_key,
            model=req.model,
            base_url=req.base_url,
            clear_key=req.clear_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/providers/{provider_name}/test")
async def test_provider_connection(provider_name: str, req: ProviderTestRequest | None = None) -> dict[str, Any]:
    body = req or ProviderTestRequest()
    try:
        return services.test_provider(
            provider_name,
            api_key=body.api_key,
            model=body.model,
            base_url=body.base_url,
            register=body.register,
            label=body.label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/settings/providers/{provider_name}/models")
async def list_provider_models(provider_name: str, req: ProviderTestRequest | None = None) -> dict[str, Any]:
    body = req or ProviderTestRequest()
    try:
        return services.list_provider_models(
            provider_name,
            api_key=body.api_key,
            base_url=body.base_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/settings/active-provider-entry")
async def set_active_provider_entry(req: SetActiveProviderEntryRequest) -> dict[str, Any]:
    try:
        return services.set_active_provider_entry(req.provider, req.entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/settings/providers/{provider_name}/entries/{entry_id}")
async def delete_provider_entry(provider_name: str, entry_id: str) -> dict[str, Any]:
    try:
        return services.delete_provider_entry(provider_name, entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/settings/provider-priority")
async def set_provider_priority(req: ProviderPriorityRequest) -> dict[str, Any]:
    try:
        return services.set_provider_priority(req.priority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# Meta: version / changelog / activity
# --------------------------------------------------------------------------- #

@app.get("/api/meta/version")
async def meta_version() -> dict[str, Any]:
    from .config import APP_VERSION
    info = services.releases.current_version()
    return {"version": APP_VERSION, **info}


@app.get("/api/meta/changelog")
async def meta_changelog(limit: int = 10) -> dict[str, Any]:
    return {"releases": services.releases.list_releases(limit=limit)}


@app.get("/api/meta/changes")
async def meta_changes(since: float = 0) -> dict[str, Any]:
    return {"changes": services.releases.list_changes_since(since)}


@app.get("/api/activity")
async def list_activity(since: float = 0, kind: str | None = None, limit: int = 100) -> dict[str, Any]:
    return {"events": services.activity.list_since(since, kind, limit)}


# --------------------------------------------------------------------------- #
# Copilot chat
# --------------------------------------------------------------------------- #

@app.post("/api/chat/sessions")
async def chat_create_session(req: ChatSessionCreateRequest | None = None) -> dict[str, Any]:
    title = (req.title if req and req.title else "") or "新对话"
    session = create_session(title=title)
    if req:
        ws = session["workspace"]
        if req.resume_text:
            ws["resume_text"] = req.resume_text
        if req.job_text:
            ws["job_text"] = req.job_text
        if req.company:
            ws["company"] = req.company
    services.store.chat_save(session["id"], session)
    return {"session": session}


@app.patch("/api/chat/sessions/{session_id}")
async def chat_update_session(session_id: str, req: ChatSessionUpdateRequest) -> dict[str, Any]:
    session = services.store.chat_get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if req.title is not None:
        session["title"] = req.title.strip()[:80] or "新对话"
    session["updated_at"] = time.time()
    services.store.chat_save(session_id, session)
    return {"session": session}


@app.delete("/api/chat/sessions/{session_id}")
async def chat_delete_session(session_id: str) -> dict[str, Any]:
    if not services.store.chat_delete(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}


@app.get("/api/chat/sessions")
async def chat_list_sessions(limit: int = 20) -> dict[str, Any]:
    return {"sessions": services.store.chat_list(limit)}


@app.get("/api/chat/sessions/{session_id}")
async def chat_get_session(session_id: str) -> dict[str, Any]:
    session = services.store.chat_get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": session}


async def _stream_copilot(coro_factory) -> StreamingResponse:
    tracer = services.new_tracer()

    async def gen():
        turn = await coro_factory(tracer)
        for event in turn.events:
            yield _sse(event)
        async for event in tracer.events():
            yield _sse(event)
        yield _sse({
            "type": "done",
            "message": turn.assistant_message,
            "session": turn.session,
            "trace": tracer.summary(),
        })
        tracer.close()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/chat/sessions/{session_id}/message")
async def chat_message(session_id: str, req: ChatMessageRequest):
    session = services.store.chat_get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    async def run(tracer: Tracer):
        return await services.copilot.handle_message(session, req.text, tracer)

    return await _stream_copilot(run)


@app.post("/api/chat/sessions/{session_id}/confirm")
async def chat_confirm(session_id: str, req: ChatConfirmRequest):
    session = services.store.chat_get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    if req.action == "reject":
        session["pending_proposal"] = None
        services.store.chat_save(session_id, session)
        return {"ok": True, "message": "已取消。"}

    async def run(tracer: Tracer):
        return await services.copilot.confirm_proposal(session, req.proposal_id, tracer)

    return await _stream_copilot(run)


@app.get("/api/runs")
async def list_runs(module: str | None = None, limit: int = 50) -> dict[str, Any]:
    return {"runs": services.store.list_runs(module, limit)}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = services.store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.get("/api/runs/{run_id}/attribution")
async def run_attribution(run_id: str) -> dict[str, Any]:
    run = services.store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    report = analyze_trace(run.get("trace") or {})
    return report.to_dict()


@app.post("/api/runs/{run_id}/replay")
async def run_replay(run_id: str) -> dict[str, Any]:
    result = await replay_run(services, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result.to_dict()


@app.get("/api/checkpoints/{cp_id}")
async def get_checkpoint(cp_id: str) -> dict[str, Any]:
    cp = services.store.checkpoint_load(cp_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="checkpoint not found")
    return {"done": cp["done"], "iteration": cp["state"].get("iteration"),
            "messages": len(cp["state"].get("messages", []))}


# --------------------------------------------------------------------------- #
# Feature endpoints
# --------------------------------------------------------------------------- #

@app.post("/api/resume/rewrite")
async def resume_rewrite(req: RewriteRequest):
    data = {"resume_text": req.resume_text, "job_text": req.job_text}
    runner = lambda t: services.rewriter.run(req.resume_text, req.job_text, t)  # noqa: E731
    if req.stream:
        return await _stream_run("resume_rewrite", data, runner)
    return await _run_json("resume_rewrite", data, runner)


@app.post("/api/match")
async def match(req: MatchRequest):
    data = {"resume_text": req.resume_text, "job_text": req.job_text}
    runner = lambda t: services.matcher.run(req.resume_text, req.job_text, t)  # noqa: E731
    if req.stream:
        return await _stream_run("matching", data, runner)
    return await _run_json("matching", data, runner)


@app.post("/api/outreach")
async def outreach(req: OutreachRequest):
    data = {"resume_text": req.resume_text, "job_text": req.job_text, "style": req.style}
    runner = lambda t: services.outreach.run(req.resume_text, req.job_text, req.style, t)  # noqa: E731
    if req.stream:
        return await _stream_run("outreach", data, runner)
    return await _run_json("outreach", data, runner)


@app.post("/api/retrospective")
async def retrospective(req: RetrospectiveRequest):
    transcript = req.transcript or ""
    if req.session_id:
        session = services.interviewer.get(req.session_id)
        stored = services.store.get_session(req.session_id)
        if session:
            transcript = session.transcript()
        elif stored:
            label = {"interviewer": "面试官", "candidate": "候选人"}
            transcript = "\n".join(
                f"{label.get(t['role'], t['role'])}: {t['content']}" for t in stored.get("turns", [])
            )
    if not transcript:
        raise HTTPException(status_code=400, detail="需要 transcript 或有效的 session_id")

    data = {"transcript": transcript, "job_text": req.job_text, "company": req.company}
    runner = lambda t: services.retrospective.run(transcript, req.job_text, req.company, t)  # noqa: E731
    if req.stream:
        return await _stream_run("retrospective", data, runner)
    return await _run_json("retrospective", data, runner)


# -- Interview (turn-based JSON) -------------------------------------------- #

@app.post("/api/interview/start")
async def interview_start(req: InterviewStartRequest) -> dict[str, Any]:
    session = services.interviewer.create(req.resume_text, req.job_text,
                                          req.language, req.max_questions)
    tracer = services.new_tracer()
    question = await services.interviewer.ask_next(session, tracer)
    services.store.save_session(session.id, session.to_dict())
    return {"session": session.to_dict(), "question": question, "trace": tracer.summary()}


@app.post("/api/interview/answer")
async def interview_answer(req: InterviewAnswerRequest) -> dict[str, Any]:
    session = services.interviewer.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session 不存在（可能服务已重启）")
    services.interviewer.answer(session, req.answer)
    tracer = services.new_tracer()
    question = await services.interviewer.ask_next(session, tracer)
    services.store.save_session(session.id, session.to_dict())
    return {"session": session.to_dict(), "question": question,
            "finished": session.finished, "trace": tracer.summary()}


@app.get("/api/interview/{session_id}")
async def interview_get(session_id: str) -> dict[str, Any]:
    session = services.interviewer.get(session_id)
    if session is not None:
        return session.to_dict()
    stored = services.store.get_session(session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="session not found")
    return stored


# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #

@app.get("/api/memory")
async def memory_list(kind: str | None = None) -> dict[str, Any]:
    return {"memories": [m.to_dict() for m in services.memory.list(kind)]}


@app.get("/api/memory/search")
async def memory_search(q: str, kind: str | None = None) -> dict[str, Any]:
    return {"memories": [m.to_dict() for m in services.memory.search(q, kind)]}


@app.post("/api/memory")
async def memory_create(req: MemoryCreateRequest) -> dict[str, Any]:
    item = services.memory.add(req.content, kind=req.kind, tags=req.tags, source="user")
    return item.to_dict()


@app.put("/api/memory/{mem_id}")
async def memory_update(mem_id: str, req: MemoryUpdateRequest) -> dict[str, Any]:
    ok = services.memory.update(mem_id, req.content, req.tags)
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"ok": True}


@app.delete("/api/memory/{mem_id}")
async def memory_delete(mem_id: str) -> dict[str, Any]:
    ok = services.memory.delete(mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Daily report (今日日报) + Obsidian export
# --------------------------------------------------------------------------- #

@app.post("/api/journal")
async def journal(req: JournalRequest = JournalRequest()) -> dict[str, Any]:
    tracer = services.new_tracer()
    result = await services.journal.run(tracer, period=req.period)
    result_dict = result.to_dict()
    run_id = services.store.save_run("journal", {}, result_dict, tracer.summary())
    return {"run_id": run_id, "result": result_dict, "trace": tracer.summary()}


@app.post("/api/journal/export")
async def journal_export() -> dict[str, Any]:
    result = await services.journal.run(services.new_tracer())
    path = services.obsidian.write(f"今日日报 {result.date}", result.markdown,
                                   subdir="日报", tags=["日报", "jobseeker"])
    return {"path": path, "date": result.date}


@app.post("/api/export/obsidian")
async def export_obsidian(req: ExportRequest) -> dict[str, Any]:
    path = services.obsidian.write(req.title, req.content, subdir=req.subdir, tags=req.tags)
    return {"path": path}


# --------------------------------------------------------------------------- #
# Governance: audit trail + HITL approvals
# --------------------------------------------------------------------------- #

@app.get("/api/audit")
async def audit_list(limit: int = 100) -> dict[str, Any]:
    return {"entries": services.store.audit_list(limit)}


@app.get("/api/approvals")
async def approvals() -> dict[str, Any]:
    return {"policy": services.approver.policy, "approved_tools": services.approver.approved_tools()}


@app.post("/api/approvals/{tool_name}")
async def approve_tool(tool_name: str) -> dict[str, Any]:
    services.approver.approve_tool(tool_name)
    services.approver.record("approve_tool", "human_approved", actor="user", tool=tool_name)
    return {"ok": True, "approved_tools": services.approver.approved_tools()}


@app.delete("/api/approvals/{tool_name}")
async def revoke_tool(tool_name: str) -> dict[str, Any]:
    services.approver.revoke_tool(tool_name)
    services.approver.record("revoke_tool", "revoked", actor="user", tool=tool_name)
    return {"ok": True, "approved_tools": services.approver.approved_tools()}


# --------------------------------------------------------------------------- #
# Verification: LLM-as-judge
# --------------------------------------------------------------------------- #

@app.post("/api/verify/judge")
async def verify_judge(req: JudgeRequest) -> dict[str, Any]:
    tracer = services.new_tracer()
    result = await services.judge.score(req.content, req.criteria or None,
                                        req.artifact_type, tracer)
    return {"result": result.to_dict(), "trace": tracer.summary()}


# --------------------------------------------------------------------------- #
# Static frontend (served when a production build exists)
# --------------------------------------------------------------------------- #

_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
