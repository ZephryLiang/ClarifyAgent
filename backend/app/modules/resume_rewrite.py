"""Module ①: grounded, anti-hallucination resume rewriting.

Rewrites resume bullet points by applying proven methodologies (XYZ, STAR,
strong action verbs, quantification) sourced from the knowledge base — never
inventing facts. When an LLM is configured the rewrite is authored by an agent
that greps/reads the KB for grounding; otherwise a deterministic heuristic path
produces suggestions with the same citations. Every rewrite is passed through a
faithfulness check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..domain import parse_resume_text
from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import extract_json, llm_available
from .grounding import FaithfulnessReport, repair, verify_faithfulness

# Weak verbs whose bullets typically need strengthening (zh + en).
_WEAK_VERBS = ["负责", "参与", "协助", "帮助", "做了", "从事", "responsible for",
               "worked on", "helped", "assisted", "participated"]
_HAS_NUMBER = re.compile(r"\d")

_SYSTEM = """你是求职 Agent 的简历改写专家。你必须严格遵守知识库中 `resume/anti_hallucination.md` 的诚信底线：
- 绝不新增候选人未提供的事实（公司/职位/时间/项目/技术/数字/奖项）。
- 不夸大角色，不把团队成果算作个人。
- 缺少量化数据时用占位符 `[待补充: ...]`，严禁编造数字。

工作流程：
1. 用 kb_list 了解可用依据，用 kb_grep/kb_read 检索相关最佳实践（XYZ 公式、STAR、强动词、量化影响、ATS）。
2. 对每条经历改写，套用方法论提升表达。
3. 每条改写必须注明引用了哪些依据（写成 `文件:行号` 或文件名）。
4. 指出需要候选人补充的信息。

只输出 JSON，格式：
{"suggestions": [{"original": "...", "rewritten": "...", "principles": ["resume/xyz_formula.md:3", ...], "needs_input": ["..."]}]}"""


@dataclass
class RewriteSuggestion:
    original: str
    rewritten: str
    principles: list[str] = field(default_factory=list)
    needs_input: list[str] = field(default_factory=list)
    faithfulness: FaithfulnessReport | None = None
    repaired: bool = False

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "rewritten": self.rewritten,
            "principles": self.principles,
            "needs_input": self.needs_input,
            "faithfulness": self.faithfulness.to_dict() if self.faithfulness else None,
            "repaired": self.repaired,
        }


@dataclass
class ResumeRewriteResult:
    suggestions: list[RewriteSuggestion] = field(default_factory=list)
    llm_used: bool = False
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "suggestions": [s.to_dict() for s in self.suggestions],
            "llm_used": self.llm_used,
            "summary": self.summary,
        }


def extract_bullets(resume_text: str) -> list[str]:
    """Pull rewrite-worthy bullet lines from resume text."""

    bullets: list[str] = []
    for line in resume_text.splitlines():
        stripped = line.strip()
        cleaned = stripped.lstrip("-*•·").strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        # Heuristic: bullets are lines that were list items or long sentences.
        if stripped[:1] in "-*•·" or len(cleaned) > 12:
            bullets.append(cleaned)
    # De-dup preserving order.
    seen, out = set(), []
    for b in bullets:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


class ResumeRewriter:
    def __init__(self, gateway: Gateway | None = None, tools: ToolRegistry | None = None,
                 approver: object | None = None) -> None:
        self.gateway = gateway
        self.tools = tools
        self.approver = approver

    async def run(self, resume_text: str, job_text: str | None = None,
                  tracer: Tracer | None = None) -> ResumeRewriteResult:
        tracer = tracer or Tracer()
        span = tracer.start_span("resume_rewrite", SpanKind.AGENT,
                                 has_llm=llm_available(self.gateway))
        try:
            if llm_available(self.gateway) and self.tools is not None:
                result = await self._run_llm(resume_text, job_text, tracer, span.id)
            else:
                result = self._run_offline(resume_text)
            # Verification closed loop: verify → auto-repair once → re-verify.
            repaired_count = 0
            for s in result.suggestions:
                s.faithfulness = verify_faithfulness(s.original, s.rewritten)
                if s.faithfulness and not s.faithfulness.ok:
                    s.rewritten = repair(s.rewritten, s.faithfulness)
                    s.faithfulness = verify_faithfulness(s.original, s.rewritten)
                    s.repaired = True
                    repaired_count += 1
                    if "存在无法核实的数据，已改为占位符待你确认。" not in s.needs_input:
                        s.needs_input.append("存在无法核实的数据，已改为占位符待你确认。")
            flagged = sum(0 if s.faithfulness and s.faithfulness.ok else 1 for s in result.suggestions)
            tracer.end_span(span, SpanStatus.OK, suggestions=len(result.suggestions),
                            flagged=flagged, repaired=repaired_count)
            return result
        except Exception as exc:  # noqa: BLE001
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            raise

    async def _run_llm(self, resume_text: str, job_text: str | None,
                       tracer: Tracer, parent_id: str) -> ResumeRewriteResult:
        assert self.gateway is not None  # guaranteed by llm_available() check
        # Restrict to KB tools so the agent grounds via grep/read.
        kb_tools = self.tools.subset(["kb_list", "kb_grep", "kb_read"]) if self.tools else ToolRegistry()
        agent = Agent(self.gateway, kb_tools, tracer, system=_SYSTEM,
                      name="resume-rewriter", temperature=0.3, parent_span_id=parent_id,
                      approver=self.approver)
        prompt = "请改写以下简历中的经历条目，逐条给出改写与依据。\n\n简历：\n" + resume_text
        if job_text:
            prompt += "\n\n目标岗位 JD（用于对齐关键词，但不得虚构技能）：\n" + job_text
        result = await agent.run(prompt)
        data = extract_json(result.output) or {}
        suggestions: list[RewriteSuggestion] = []
        for item in (data.get("suggestions", []) if isinstance(data, dict) else []):
            suggestions.append(RewriteSuggestion(
                original=str(item.get("original", "")),
                rewritten=str(item.get("rewritten", "")),
                principles=[str(p) for p in item.get("principles", [])],
                needs_input=[str(n) for n in item.get("needs_input", [])],
            ))
        if not suggestions:
            # Model returned prose instead of JSON — fall back to offline.
            return self._run_offline(resume_text)
        return ResumeRewriteResult(suggestions=suggestions, llm_used=True,
                                   summary=f"基于知识库改写了 {len(suggestions)} 条经历。")

    def _run_offline(self, resume_text: str) -> ResumeRewriteResult:
        # Prefer the parsed experience/highlight bullets; fall back to raw lines.
        parsed = parse_resume_text(resume_text)
        bullets = parsed.experiences + parsed.highlights
        if not bullets:
            bullets = extract_bullets(resume_text)
        suggestions: list[RewriteSuggestion] = []
        for b in bullets:
            principles: list[str] = []
            needs: list[str] = []
            rewritten = b

            weak = next((w for w in _WEAK_VERBS if w in b.lower()), None)
            if weak:
                principles.append("resume/action_verbs.md")
                rewritten = re.sub(r"^(负责|参与|协助|帮助|从事)\s*", "主导/推动 ", rewritten)
                needs.append("确认你在该经历中的真实角色（主导/参与），据实选择动词。")

            if not _HAS_NUMBER.search(b):
                principles.append("resume/quantify_impact.md")
                principles.append("resume/xyz_formula.md")
                rewritten = rewritten.rstrip("。.") + "，量化成果 [待补充: 例如 提升X% / 支撑Y QPS / 节省Z小时]。"
                needs.append("补充可量化的结果数据（性能/规模/效率/业务指标）。")

            if rewritten != b or principles:
                suggestions.append(RewriteSuggestion(
                    original=b, rewritten=rewritten, principles=principles, needs_input=needs,
                ))
        summary = (
            f"离线规则引擎给出 {len(suggestions)} 条改写建议（未启用大模型）。"
            "配置任一 LLM provider 可获得更自然的改写。"
        )
        return ResumeRewriteResult(suggestions=suggestions, llm_used=False, summary=summary)
