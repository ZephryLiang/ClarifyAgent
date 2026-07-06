"""Module ②: job matching with parallel subagents.

Always computes a deterministic skill/experience match from the domain layer.
When an LLM is available, it additionally spawns parallel subagents — JD
analysis, resume analysis, and company research (web search) — and synthesises
them into a qualitative report on top of the objective score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import compute_match, parse_job_text, parse_resume_text
from ..domain.models import MatchResult
from ..gateway.registry import Gateway
from ..harness import Orchestrator, SubagentTask, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import llm_available


@dataclass
class MatchReport:
    match: MatchResult | None = None
    analyses: dict = field(default_factory=dict)  # subagent name -> text
    synthesis: str = ""
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {
            "match": self.match.to_dict() if self.match else None,
            "analyses": self.analyses,
            "synthesis": self.synthesis,
            "llm_used": self.llm_used,
        }


class Matcher:
    def __init__(self, gateway: Gateway | None = None, tools: ToolRegistry | None = None) -> None:
        self.gateway = gateway
        self.tools = tools

    async def run(self, resume_text: str, job_text: str,
                  tracer: Tracer | None = None) -> MatchReport:
        tracer = tracer or Tracer()
        span = tracer.start_span("matching", SpanKind.AGENT, has_llm=llm_available(self.gateway))
        try:
            resume = parse_resume_text(resume_text)
            job = parse_job_text(job_text)
            match = compute_match(resume, job)

            if not (llm_available(self.gateway) and self.tools is not None):
                tracer.end_span(span, SpanStatus.OK, mode="offline", score=match.score)
                return MatchReport(match=match, synthesis=match.recommendation, llm_used=False)

            assert self.gateway is not None
            orchestrator = Orchestrator(self.gateway, self.tools, tracer, max_iterations=4)
            company = job.company or "该公司"
            tasks = [
                SubagentTask(
                    name="jd-analysis",
                    system="你是资深技术招聘官，客观分析岗位要求。",
                    prompt=f"分析这份岗位JD的核心硬性要求、隐含期望与考察重点，简洁列点：\n{job_text}",
                    tool_names=[],
                ),
                SubagentTask(
                    name="resume-analysis",
                    system="你是资深职业顾问，客观分析候选人简历。",
                    prompt=f"分析候选人的核心优势与潜在短板，简洁列点：\n{resume_text}",
                    tool_names=[],
                ),
                SubagentTask(
                    name="company-research",
                    system="你是行业研究员，用 web_search 调研公司背景。若搜索不可用则基于常识给出注意事项。",
                    prompt=f"简要调研「{company}」的业务方向、技术栈与面试关注点，给出投递建议。",
                    tool_names=["web_search"],
                ),
            ]
            outcomes = await orchestrator.run_parallel(tasks, parent_span_id=span.id)
            analyses = {o.name: (o.output if o.ok else f"(失败: {o.error})") for o in outcomes}

            synthesis = await self._synthesize(match, analyses, tracer, span.id)
            tracer.end_span(span, SpanStatus.OK, mode="agentic", score=match.score)
            return MatchReport(match=match, analyses=analyses, synthesis=synthesis, llm_used=True)
        except Exception as exc:  # noqa: BLE001
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            raise

    async def _synthesize(self, match: MatchResult, analyses: dict,
                          tracer: Tracer, parent_id: str) -> str:
        from ..harness import Agent

        assert self.gateway is not None
        agent = Agent(self.gateway, ToolRegistry(), tracer,
                      system="你是求职策略顾问，综合各方分析给出可执行的投递建议。",
                      name="match-synthesis", temperature=0.4, parent_span_id=parent_id)
        prompt = (
            f"客观匹配度评分：{match.score}/100（{match.verdict}）。\n"
            f"已匹配技能：{match.matched_skills}\n缺失硬性技能：{match.missing_required}\n\n"
            f"岗位分析：\n{analyses.get('jd-analysis','')}\n\n"
            f"简历分析：\n{analyses.get('resume-analysis','')}\n\n"
            f"公司调研：\n{analyses.get('company-research','')}\n\n"
            "请给出：是否值得投递、投递前需要突出/补齐什么、以及一句话总体建议。"
        )
        result = await agent.run(prompt)
        return result.output
