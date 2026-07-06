"""FastAPI application: REST endpoints + SSE streaming of agent traces."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .harness import Tracer
from .schemas import (
    InterviewAnswerRequest,
    InterviewStartRequest,
    MatchRequest,
    OutreachRequest,
    RetrospectiveRequest,
    RewriteRequest,
)
from .service import AppServices

app = FastAPI(title="求职 Agent", version="0.1.0",
              description="Agentic job-seeking assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

services: AppServices = AppServices()


@app.on_event("startup")
async def _startup() -> None:
    await services.connect_mcp()


@app.on_event("shutdown")
async def _shutdown() -> None:
    await services.shutdown()


# --------------------------------------------------------------------------- #
# SSE helper
# --------------------------------------------------------------------------- #

def _sse(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _stream_run(
    module: str,
    input_data: Dict[str, Any],
    runner: Callable[[Tracer], Awaitable[Any]],
) -> StreamingResponse:
    """Run ``runner`` while streaming its trace events, then emit the result."""

    tracer = services.new_tracer()

    async def watch() -> Any:
        try:
            return await runner(tracer)
        finally:
            tracer.close()

    async def gen():
        watcher = asyncio.create_task(watch())
        try:
            async for event in tracer.events():
                yield _sse(event)
            result = await watcher
            result_dict = result.to_dict() if hasattr(result, "to_dict") else result
            run_id = services.store.save_run(module, input_data, result_dict, tracer.summary())
            yield _sse({"type": "result", "run_id": run_id,
                        "result": result_dict, "trace": tracer.summary()})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def _run_json(module: str, input_data: Dict[str, Any],
                    runner: Callable[[Tracer], Awaitable[Any]]) -> Dict[str, Any]:
    tracer = services.new_tracer()
    result = await runner(tracer)
    result_dict = result.to_dict() if hasattr(result, "to_dict") else result
    run_id = services.store.save_run(module, input_data, result_dict, tracer.summary())
    return {"run_id": run_id, "result": result_dict, "trace": tracer.summary()}


# --------------------------------------------------------------------------- #
# Meta endpoints
# --------------------------------------------------------------------------- #

@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
async def status() -> Dict[str, Any]:
    return services.status()


@app.get("/api/runs")
async def list_runs(module: str | None = None, limit: int = 50) -> Dict[str, Any]:
    return {"runs": services.store.list_runs(module, limit)}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    run = services.store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run


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
async def interview_start(req: InterviewStartRequest) -> Dict[str, Any]:
    session = services.interviewer.create(req.resume_text, req.job_text,
                                          req.language, req.max_questions)
    tracer = services.new_tracer()
    question = await services.interviewer.ask_next(session, tracer)
    services.store.save_session(session.id, session.to_dict())
    return {"session": session.to_dict(), "question": question, "trace": tracer.summary()}


@app.post("/api/interview/answer")
async def interview_answer(req: InterviewAnswerRequest) -> Dict[str, Any]:
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
async def interview_get(session_id: str) -> Dict[str, Any]:
    session = services.interviewer.get(session_id)
    if session is not None:
        return session.to_dict()
    stored = services.store.get_session(session_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="session not found")
    return stored


# --------------------------------------------------------------------------- #
# Static frontend (served when a production build exists)
# --------------------------------------------------------------------------- #

_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
