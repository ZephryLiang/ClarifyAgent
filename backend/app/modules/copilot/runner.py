"""JobSeeker Copilot orchestrator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ...domain import compute_match, parse_job_text, parse_resume_text
from ...gateway.base import Message
from ...harness import Agent, Tracer
from ...harness.trace import SpanKind, SpanStatus
from ..activity_ledger import ActivityLedger
from ..base import llm_available
from .context import CopilotContext, new_session, touch_session_meta
from .tools import _LONG_TEXT, _is_job, _is_resume, build_copilot_tools

_SYSTEM = """你是 ClarifyAgent 求职 Copilot。帮助用户对话式完成：JD 解读、公司调研、简历匹配、Gap 分析、技术调研、学习计划、改写、打招呼。

规则：
1. 用户粘贴大段文本 → 先 update_workspace，不要擅自跑重流程。
2. 识别意图后**询问**用户要：只解读 JD / 调研公司 / 简历匹配 / 其他；不要替用户决定。
3. 重操作必须先 propose_*，等用户 confirm 后再 run_*（proposal_id 由 confirm API 注入）。
4. 匹配分低时建议深度 Gap 分析，但不要自动执行。
5. 项目建议需先 tech research；reframe/改写遵守反幻觉。
6. 模拟面试、复盘、日报/周报可通过 propose/run 或 generate_journal 完成。
7. 用中文回复，简洁，每步结束给出 2-4 个明确下一步选项。

可用工具见 registry；run_* 工具仅在消息含 [CONFIRMED:proposal_id] 时调用。"""


@dataclass
class CopilotTurn:
    assistant_message: str
    events: list[dict[str, Any]]
    session: dict[str, Any]

    def to_dict(self) -> dict:
        return {
            "message": self.assistant_message,
            "events": self.events,
            "session": self.session,
        }


class JobSeekerCopilot:
    def __init__(self, services: Any) -> None:
        self.services = services

    async def handle_message(
        self,
        session: dict[str, Any],
        text: str,
        tracer: Tracer | None = None,
    ) -> CopilotTurn:
        tracer = tracer or Tracer()
        ledger = ActivityLedger(self.services.store)
        ctx = CopilotContext(session=session, services=self.services, tracer=tracer, ledger=ledger)
        ctx.add_message("user", text)

        gw = self.services.gateway
        if gw.llm_mode == "online" and not gw.providers_configured():
            reply = (
                "当前为在线模式，但未检测到可用的 LLM API Key。"
                "请在「LLM Gateway」Tab 或 backend/.env 配置 provider key，或切换为自动/离线。"
            )
            ctx.add_message("assistant", reply)
            self.services.store.chat_save(session["id"], session)
            return CopilotTurn(reply, ctx.events, session)

        if not llm_available(gw):
            reply = await self._offline_reply(ctx, text, tracer)
            ctx.add_message("assistant", reply)
            self.services.store.chat_save(session["id"], session)
            return CopilotTurn(reply, ctx.events, session)

        tools = build_copilot_tools(ctx)
        agent = Agent(
            self.services.gateway,
            tools,
            tracer,
            system=_SYSTEM,
            name="job-seeker-copilot",
            temperature=0.4,
            approver=self.services.approver,
        )
        history = [Message(role=m["role"], content=m["content"]) for m in session["messages"][:-1]]
        span = tracer.start_span("copilot-turn", SpanKind.AGENT)
        try:
            result = await agent.run(text, history=history)
            reply = result.output.strip() or "已完成。请查看右侧 Artifact 或继续说明下一步。"
            ctx.add_message("assistant", reply)
            tracer.end_span(span, SpanStatus.OK)
        except Exception as exc:  # noqa: BLE001
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            reply = f"处理时出错: {exc}"
            ctx.add_message("assistant", reply)

        self.services.store.chat_save(session["id"], session)
        return CopilotTurn(reply, ctx.events, session)

    async def confirm_proposal(
        self,
        session: dict[str, Any],
        proposal_id: str,
        tracer: Tracer | None = None,
    ) -> CopilotTurn:
        tracer = tracer or Tracer()
        prop = session.get("pending_proposal")
        if not prop or prop.get("id") != proposal_id:
            return CopilotTurn("找不到待确认的提议，可能已过期。", [], session)

        prompt = f"[CONFIRMED:{proposal_id}] 用户已确认。请立即调用对应的 run_* 工具执行，proposal_id={proposal_id}。"
        session["proposal_approved_id"] = proposal_id
        return await self.handle_message(session, prompt, tracer)

    async def _offline_reply(self, ctx: CopilotContext, text: str, tracer: Tracer | None = None) -> str:
        ws = ctx.workspace
        if len(text.strip()) > _LONG_TEXT:
            if _is_job(text):
                ws["job_text"] = text.strip()
                from ...domain import parse_job_text
                job = parse_job_text(text)
                ws["company"] = job.company
                ws["role"] = job.title
                ws.setdefault("jobs", []).append({
                    "id": text[:8], "company": job.company, "role": job.title, "text": text.strip(),
                })
                ctx.log_activity("capture_jd", f"保存 JD · {job.company}")
                touch_session_meta(session, job.company or job.title)
                return (
                    f"已保存 JD（{job.company} · {job.title}）。\n"
                    "离线模式：可选 [只解读 JD] [快速匹配-需简历] [继续添加 JD]。"
                )
            if _is_resume(text):
                ws["resume_text"] = text.strip()
                ctx.log_activity("capture_resume", "保存简历")
                return "已保存简历。离线可用 skill_match（需 JD）。请粘贴 JD 或说「快速匹配」。"
        if re.search(r"快速|匹配|score", text, re.I):
            if ws.get("resume_text") and ws.get("job_text"):
                m = compute_match(parse_resume_text(ws["resume_text"]), parse_job_text(ws["job_text"]))
                ctx.add_artifact("quick_score", m.to_dict())
                return f"快速匹配 {m.score}/100（{m.verdict}）。配置 LLM 后可做完整报告。"
            return "请先粘贴简历和 JD。"
        if re.search(r"周报|journal|今天", text, re.I):
            period = "week" if re.search(r"周报|week", text, re.I) else "day"
            result = await self.services.journal.run(tracer or Tracer(), period=period)
            data = result.to_dict() if hasattr(result, "to_dict") else result
            ctx.add_artifact("journal", data if isinstance(data, dict) else {"markdown": str(data)})
            label = "周报" if period == "week" else "日报"
            md = data.get("markdown", "") if isinstance(data, dict) else str(data)
            return f"已生成{label}（见右侧 Artifact）。\n\n{md[:800]}"
        return (
            "离线 Copilot：粘贴 JD 或简历我会保存到工作区。"
            "配置 LLM key 后可对话解读、调研、完整匹配。"
        )


def create_session(title: str = "新对话") -> dict[str, Any]:
    return new_session(title=title)
