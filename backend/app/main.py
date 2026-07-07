"""FastAPI application: REST endpoints + SSE streaming of agent traces."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .evals import replay_run
from .harness import Tracer
from .observability import analyze_trace
from .schemas import (
    ExportRequest,
    InterviewAnswerRequest,
    InterviewStartRequest,
    JudgeRequest,
    MatchRequest,
    MemoryCreateRequest,
    MemoryUpdateRequest,
    OutreachRequest,
    RetrospectiveRequest,
    RewriteRequest,
)
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
async def journal() -> dict[str, Any]:
    tracer = services.new_tracer()
    result = await services.journal.run(tracer)
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
