"""Module ③: outreach / greeting message ("打招呼") generation."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import compute_match, parse_job_text, parse_resume_text
from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import llm_available

_STYLES = {
    "professional": "专业稳重",
    "warm": "亲切热情",
    "concise": "简洁直接",
}

_SYSTEM = """你是求职 Agent 的沟通专家。为候选人写一条在招聘平台上主动打招呼的开场消息。
要求：2-4 句、80 字以内、真诚具体不套路；点出与岗位最契合的 1-2 个技能；结尾自然引导对话。
只输出消息正文，不要解释。语言与岗位JD一致（中文或英文）。"""


@dataclass
class OutreachResult:
    message: str = ""
    variants: list[str] = field(default_factory=list)
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {"message": self.message, "variants": self.variants, "llm_used": self.llm_used}


class OutreachWriter:
    def __init__(self, gateway: Gateway | None = None) -> None:
        self.gateway = gateway

    async def run(self, resume_text: str, job_text: str, style: str = "professional",
                  tracer: Tracer | None = None) -> OutreachResult:
        tracer = tracer or Tracer()
        span = tracer.start_span("outreach", SpanKind.AGENT, style=style,
                                 has_llm=llm_available(self.gateway))
        try:
            resume = parse_resume_text(resume_text)
            job = parse_job_text(job_text)
            match = compute_match(resume, job)

            if llm_available(self.gateway):
                assert self.gateway is not None
                agent = Agent(self.gateway, ToolRegistry(), tracer, system=_SYSTEM,
                              name="outreach-writer", temperature=0.7, parent_span_id=span.id)
                matched = "、".join(match.matched_skills[:4]) or "、".join(resume.skills[:4])
                prompt = (
                    f"风格：{_STYLES.get(style, '专业稳重')}\n"
                    f"候选人职位：{resume.title or '工程师'}，经验：{resume.years_experience:g} 年\n"
                    f"契合技能：{matched}\n目标岗位：{job.title}（{job.company or ''}）\n"
                    "请写一条打招呼消息。"
                )
                result = await agent.run(prompt)
                msg = result.output.strip()
                tracer.end_span(span, SpanStatus.OK, mode="agentic")
                return OutreachResult(message=msg, variants=[msg], llm_used=True)

            msg = self._template(resume, job, match)
            tracer.end_span(span, SpanStatus.OK, mode="offline")
            return OutreachResult(message=msg, variants=[msg], llm_used=False)
        except Exception as exc:  # noqa: BLE001
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            raise

    @staticmethod
    def _template(resume, job, match) -> str:
        role = job.title or "该职位"
        matched = (match.matched_skills or resume.skills)[:3]
        matched_str = "、".join(matched) if matched else "相关技术"
        exp = f"{resume.years_experience:g} 年" if resume.years_experience else "扎实的"
        title = resume.title or "工程师"
        return (
            f"您好！我是一名{title}，有{exp}经验，擅长 {matched_str}，"
            f"对贵司的「{role}」很感兴趣。我的背景与岗位要求比较契合，"
            "方便的话希望能进一步了解，谢谢！"
        )
