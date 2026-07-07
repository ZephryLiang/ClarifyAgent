"""Copilot-facing tools that mutate session workspace and call feature modules."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from ...domain import compute_match, parse_job_text, parse_resume_text
from ...harness.tools import Tool, ToolRegistry, ToolResult
from .context import CopilotContext

_LONG_TEXT = 280


def _is_resume(text: str) -> bool:
    hints = ["工作经历", "项目经验", "教育背景", "resume", "experience", "education"]
    return sum(1 for h in hints if h.lower() in text.lower()) >= 2


def _is_job(text: str) -> bool:
    hints = ["任职要求", "岗位职责", "requirements", "responsibilities", "qualifications"]
    return sum(1 for h in hints if h.lower() in text.lower()) >= 1 or len(text) > 400


class UpdateWorkspaceTool(Tool):
    name = "update_workspace"
    description = (
        "保存/更新工作区字段：resume_text, job_text, company, role。"
        "当用户粘贴大段文本时调用，自动识别是简历还是 JD。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "用户粘贴的文本"},
            "field": {"type": "string", "enum": ["resume", "job", "auto"], "default": "auto"},
            "company": {"type": "string"},
            "role": {"type": "string"},
        },
        "required": ["text"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, text: str, field: str = "auto", company: str = "", role: str = "", **_: Any) -> ToolResult:  # noqa: E501
        ws = self.ctx.workspace
        kind = field
        if field == "auto":
            kind = "resume" if _is_resume(text) and not _is_job(text) else "job"
            if _is_resume(text) and _is_job(text):
                kind = "job" if len(text) > 600 else "resume"
        if kind == "resume":
            ws["resume_text"] = text.strip()
            self.ctx.log_activity("capture_resume", "保存简历到工作区")
            return ToolResult(content="已保存为简历 (resume_text)。")
        ws["job_text"] = text.strip()
        job = parse_job_text(text)
        ws["company"] = company or job.company or ws.get("company", "")
        ws["role"] = role or job.title or ws.get("role", "")
        job_entry = {
            "id": uuid.uuid4().hex[:8],
            "company": ws["company"],
            "role": ws["role"],
            "text": text.strip(),
        }
        ws.setdefault("jobs", []).append(job_entry)
        self.ctx.log_activity("capture_jd", f"保存 JD · {ws['company'] or '未知'}")
        return ToolResult(content=f"已保存 JD（{ws['company']} · {ws['role']}）。")


class RunJDAnalysisTool(Tool):
    name = "run_jd_analysis"
    description = "仅解读当前工作区 JD，不需要简历，不需要 web_search。用户明确要求「只分析 JD」时使用。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        job_text = self.ctx.workspace.get("job_text", "")
        if not job_text:
            return ToolResult(content="工作区尚无 JD，请先让用户粘贴。", is_error=True)
        analysis = await self.ctx.services.jd_analyzer.run(job_text, self.ctx.tracer)
        art_id = self.ctx.add_artifact("jd_analysis", analysis.to_dict())
        self.ctx.log_activity("jd_analysis", f"JD 解读 · {analysis.company}", artifact_ids=[art_id])
        return ToolResult(content=json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2))


class ResearchCompanyTool(Tool):
    name = "research_company"
    description = "调研公司背景（web_search）。需用户同意调研后调用。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "company": {"type": "string"},
            "role": {"type": "string"},
        },
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, company: str = "", role: str = "", **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        company = company or ws.get("company") or "目标公司"
        role = role or ws.get("role") or ""
        query = f"{company} {role} 技术栈 工程文化 面试"
        tool = self.ctx.services.tools.get("web_search")
        if tool is None:
            data = {"company": company, "summary": "web_search 不可用，请配置网络或安装 ddgs。"}
            self.ctx.add_artifact("company_research", data)
            return ToolResult(content=data["summary"], is_error=True)
        result = await tool.run(query=query, max_results=5)
        data = {"company": company, "role": role, "query": query, "findings": result.content}
        art_id = self.ctx.add_artifact("company_research", data)
        self.ctx.log_activity("company_research", f"调研 {company}", artifact_ids=[art_id])
        return ToolResult(content=result.content)


class QuickMatchTool(Tool):
    name = "quick_match"
    description = "快速确定性技能匹配打分（秒级，无需 LLM subagent）。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        if not ws.get("resume_text") or not ws.get("job_text"):
            return ToolResult(content="需要工作区中同时有 resume_text 和 job_text。", is_error=True)
        resume = parse_resume_text(ws["resume_text"])
        job = parse_job_text(ws["job_text"])
        match = compute_match(resume, job)
        payload = match.to_dict()
        art_id = self.ctx.add_artifact("quick_score", payload)
        self.ctx.log_activity("quick_match", f"快速匹配 {match.score} 分", artifact_ids=[art_id])
        return ToolResult(content=json.dumps(payload, ensure_ascii=False, indent=2), data=match)


class ProposeMatchTool(Tool):
    name = "propose_match_analysis"
    description = "提议做完整匹配报告（3 并行 subagent）。不执行，只创建待确认 proposal。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        if not ws.get("resume_text") or not ws.get("job_text"):
            return ToolResult(content="需要简历和 JD。", is_error=True)
        prop_id = self.ctx.set_proposal(
            "match",
            "完整匹配报告（JD/简历/公司 三路分析，约 30-60 秒）",
            {"resume_text": ws["resume_text"], "job_text": ws["job_text"]},
        )
        return ToolResult(content=f"已创建待确认 proposal {prop_id}，请用户确认后调用 run_match_analysis。")


class RunMatchTool(Tool):
    name = "run_match_analysis"
    description = "执行完整匹配分析。仅在用户已通过 confirm 批准 proposal 后调用。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": ["proposal_id"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, proposal_id: str, **_: Any) -> ToolResult:
        prop = self.ctx.consume_proposal(proposal_id)
        if prop is None:
            return ToolResult(content="proposal 未批准或不存在。请先 propose 并等用户 confirm。", is_error=True)
        inputs = prop["inputs"]
        report = await self.ctx.services.matcher.run(
            inputs["resume_text"], inputs["job_text"], self.ctx.tracer,
        )
        data = report.to_dict()
        art_id = self.ctx.add_artifact("match_report", data)
        score = (data.get("match") or {}).get("score", "?")
        self.ctx.log_activity("match", f"完整匹配 · {score} 分", artifact_ids=[art_id])
        return ToolResult(content=json.dumps(data, ensure_ascii=False)[:4000])


class ProposeRewriteTool(Tool):
    name = "propose_resume_rewrite"
    description = "提议有依据地改写简历。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        if not ws.get("resume_text"):
            return ToolResult(content="需要 resume_text。", is_error=True)
        prop_id = self.ctx.set_proposal("rewrite", "有依据简历改写（KB + 反幻觉校验）", {
            "resume_text": ws["resume_text"],
            "job_text": ws.get("job_text") or "",
        })
        return ToolResult(content=f"proposal {prop_id} 已创建。")


class RunRewriteTool(Tool):
    name = "run_resume_rewrite"
    description = "执行简历改写（需已 confirm proposal）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": ["proposal_id"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, proposal_id: str, **_: Any) -> ToolResult:
        prop = self.ctx.consume_proposal(proposal_id)
        if prop is None:
            return ToolResult(content="proposal 未批准。", is_error=True)
        inputs = prop["inputs"]
        result = await self.ctx.services.rewriter.run(
            inputs["resume_text"], inputs.get("job_text") or None, self.ctx.tracer,
        )
        data = result.to_dict()
        art_id = self.ctx.add_artifact("rewrite_suggestions", data)
        self.ctx.log_activity("rewrite", f"改写 {len(data.get('suggestions', []))} 条", artifact_ids=[art_id])
        return ToolResult(content=json.dumps(data, ensure_ascii=False)[:3000])


class ProposeOutreachTool(Tool):
    name = "propose_outreach"
    description = "提议生成打招呼消息。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        if not ws.get("resume_text") or not ws.get("job_text"):
            return ToolResult(content="需要 resume 和 job。", is_error=True)
        prop_id = self.ctx.set_proposal("outreach", "生成多风格打招呼消息", {
            "resume_text": ws["resume_text"],
            "job_text": ws["job_text"],
            "style": "professional",
        })
        return ToolResult(content=f"proposal {prop_id} 已创建。")


class RunOutreachTool(Tool):
    name = "run_outreach"
    description = "执行打招呼生成（需已 confirm）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": ["proposal_id"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, proposal_id: str, **_: Any) -> ToolResult:
        prop = self.ctx.consume_proposal(proposal_id)
        if prop is None:
            return ToolResult(content="proposal 未批准。", is_error=True)
        inputs = prop["inputs"]
        result = await self.ctx.services.outreach.run(
            inputs["resume_text"], inputs["job_text"], inputs.get("style", "professional"), self.ctx.tracer,
        )
        data = result.to_dict()
        art_id = self.ctx.add_artifact("outreach_messages", data)
        self.ctx.log_activity("outreach", "生成打招呼", artifact_ids=[art_id])
        return ToolResult(content=data.get("message", ""))


class ProposeGapTool(Tool):
    name = "propose_deep_gap_analysis"
    description = "提议深度 Gap 分析（语义级 gap + 桥接策略）。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        if not ws.get("resume_text") or not ws.get("job_text"):
            return ToolResult(content="需要 resume 和 job。", is_error=True)
        prop_id = self.ctx.set_proposal("gap", "深度 Gap 分析", {
            "resume_text": ws["resume_text"],
            "job_text": ws["job_text"],
        })
        return ToolResult(content=f"proposal {prop_id} 已创建。")


class RunGapTool(Tool):
    name = "run_deep_gap_analysis"
    description = "执行深度 Gap 分析（需 confirm）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": ["proposal_id"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, proposal_id: str, **_: Any) -> ToolResult:
        prop = self.ctx.consume_proposal(proposal_id)
        if prop is None:
            return ToolResult(content="proposal 未批准。", is_error=True)
        inputs = prop["inputs"]
        result = await self.ctx.services.gap_analyzer.run(
            inputs["resume_text"], inputs["job_text"], self.ctx.tracer,
        )
        data = result.to_dict()
        art_id = self.ctx.add_artifact("gap_analysis", data)
        self.ctx.log_activity("gap", "深度 Gap 分析", artifact_ids=[art_id])
        return ToolResult(content=json.dumps(data, ensure_ascii=False)[:3000])


class ProposeTechResearchTool(Tool):
    name = "propose_tech_research"
    description = "提议多源技术调研（论文/博客/GitHub/面经）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"theme": {"type": "string", "description": "调研主题，如 agent runtime"}},
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, theme: str = "", **_: Any) -> ToolResult:
        theme = theme or self.ctx.workspace.get("role") or "target skill gap"
        prop_id = self.ctx.set_proposal("tech_research", f"技术调研 · {theme}（约 1-2 分钟）", {"theme": theme})
        return ToolResult(content=f"proposal {prop_id} 已创建。")


class RunTechResearchTool(Tool):
    name = "run_tech_research"
    description = "执行技术调研（需 confirm）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": ["proposal_id"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, proposal_id: str, **_: Any) -> ToolResult:
        prop = self.ctx.consume_proposal(proposal_id)
        if prop is None:
            return ToolResult(content="proposal 未批准。", is_error=True)
        theme = prop["inputs"].get("theme", "technology")
        digest = await self.ctx.services.tech_research.run(theme, self.ctx.tracer)
        data = digest.to_dict()
        art_id = self.ctx.add_artifact("tech_research_digest", data)
        proposal = await self.ctx.services.project_advisor.propose_from_research(
            theme, digest, self.ctx.tracer,
        )
        prop_art = self.ctx.add_artifact("project_proposal", proposal.to_dict())
        self.ctx.services.research_curator.curate(digest)
        self.ctx.log_activity("tech_research", f"调研 {theme}", artifact_ids=[art_id, prop_art])
        return ToolResult(content=json.dumps(data, ensure_ascii=False)[:3000])


class ProposeLearningPlanTool(Tool):
    name = "propose_learning_plan"
    description = "提议基于多 JD 共性的学习计划。需 workspace.jobs >= 2 或用户明确指定。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "weeks": {"type": "integer"},
            "hours_per_week": {"type": "integer"},
        },
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, weeks: int = 0, hours_per_week: int = 0, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        if weeks:
            ws["time_budget"] = {"weeks": weeks, "hours_per_week": hours_per_week or 10}
        prop_id = self.ctx.set_proposal("learning_plan", "生成有限时间学习计划", {
            "time_budget": ws.get("time_budget", {"weeks": 4, "hours_per_week": 10}),
        })
        return ToolResult(content=f"proposal {prop_id} 已创建。")


class RunLearningPlanTool(Tool):
    name = "run_learning_plan"
    description = "执行学习计划生成（需 confirm）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": ["proposal_id"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, proposal_id: str, **_: Any) -> ToolResult:
        prop = self.ctx.consume_proposal(proposal_id)
        if prop is None:
            return ToolResult(content="proposal 未批准。", is_error=True)
        ws = self.ctx.workspace
        matrix = self.ctx.services.requirement_synth.synthesize(ws)
        plan = self.ctx.services.learning_plan.generate(
            matrix, ws.get("time_budget", {}), ws.get("resume_text", ""),
        )
        m_art = self.ctx.add_artifact("requirement_matrix", matrix.to_dict())
        p_art = self.ctx.add_artifact("learning_plan", plan.to_dict())
        self.ctx.log_activity("learning_plan", "生成学习计划", artifact_ids=[m_art, p_art])
        return ToolResult(content=json.dumps(plan.to_dict(), ensure_ascii=False)[:3000])


class RunRequirementSynthesisTool(Tool):
    name = "run_requirement_synthesis"
    description = "聚合 workspace 中多个 JD 的共性要求（≥2 JD）。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        if len(ws.get("jobs", [])) < 2 and not ws.get("job_text"):
            return ToolResult(content="需要至少 2 份 JD（继续粘贴或 add_job）。", is_error=True)
        matrix = self.ctx.services.requirement_synth.synthesize(ws)
        art_id = self.ctx.add_artifact("requirement_matrix", matrix.to_dict())
        self.ctx.log_activity("requirement_synthesis", f"聚合 {matrix.job_count} 份 JD", artifact_ids=[art_id])
        return ToolResult(content=json.dumps(matrix.to_dict(), ensure_ascii=False, indent=2))


class AssessRoleTool(Tool):
    name = "assess_role"
    description = "评估岗位类型、成长性、利弊取舍。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        assessment = await self.ctx.services.role_assessor.run(
            ws.get("job_text", ""), ws.get("company", ""), self.ctx.tracer,
        )
        ws.setdefault("role_assessments", []).append(assessment.to_dict())
        art_id = self.ctx.add_artifact("role_assessment", assessment.to_dict())
        if len(ws.get("role_assessments", [])) >= 2:
            report = self.ctx.services.job_market.aggregate(ws)
            self.ctx.add_artifact("job_market_report", report.to_dict())
        self.ctx.log_activity("role_assessment", assessment.role_type_label, artifact_ids=[art_id])
        return ToolResult(content=json.dumps(assessment.to_dict(), ensure_ascii=False, indent=2))


class ReviseLearningPlanTool(Tool):
    name = "revise_learning_plan"
    description = "根据用户自然语言调整学习计划（升/降优先级、改周期）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "instruction": {"type": "string", "description": "用户的调整意图原文"},
        },
        "required": ["instruction"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, instruction: str, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        matrix = self.ctx.services.requirement_synth.synthesize(ws)
        matrix = self.ctx.services.learning_plan.apply_revision(matrix, instruction)
        plan = self.ctx.services.learning_plan.generate(
            matrix, ws.get("time_budget", {}), ws.get("resume_text", ""),
        )
        self.ctx.add_artifact("requirement_matrix", matrix.to_dict())
        art_id = self.ctx.add_artifact("learning_plan", plan.to_dict())
        self.ctx.log_activity("revise_plan", instruction[:80], artifact_ids=[art_id])
        return ToolResult(content=json.dumps(plan.to_dict(), ensure_ascii=False)[:3000])


class ProposeMockInterviewTool(Tool):
    name = "propose_mock_interview"
    description = "提议开始模拟面试（多轮，需 resume + JD）。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        if not ws.get("resume_text") or not ws.get("job_text"):
            return ToolResult(content="需要 resume_text 和 job_text。", is_error=True)
        prop_id = self.ctx.set_proposal(
            "mock_interview",
            f"模拟面试 · {ws.get('company') or '目标岗位'}（约 6 轮）",
            {"resume_text": ws["resume_text"], "job_text": ws["job_text"], "language": ws.get("language", "zh")},
        )
        return ToolResult(content=f"proposal {prop_id} 已创建。")


class RunMockInterviewTool(Tool):
    name = "run_mock_interview"
    description = "启动模拟面试并返回第一个问题（需 confirm proposal）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": ["proposal_id"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, proposal_id: str, **_: Any) -> ToolResult:
        prop = self.ctx.consume_proposal(proposal_id)
        if prop is None:
            return ToolResult(content="proposal 未批准。", is_error=True)
        inputs = prop["inputs"]
        session = self.ctx.services.interviewer.create(
            inputs["resume_text"], inputs["job_text"], language=inputs.get("language", "zh"),
        )
        question = await self.ctx.services.interviewer.ask_next(session, self.ctx.tracer)
        ws = self.ctx.workspace
        ws["interview_session_id"] = session.id
        data = session.to_dict()
        data["first_question"] = question
        art_id = self.ctx.add_artifact("mock_interview", data)
        self.ctx.log_activity("mock_interview", "开始模拟面试", artifact_ids=[art_id])
        return ToolResult(content=f"面试官: {question}\n(session_id={session.id}，继续回答请用「模拟面试」Tab)")


class ProposeRetrospectiveTool(Tool):
    name = "propose_retrospective"
    description = "提议对面试 transcript 做复盘分析。"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, **_: Any) -> ToolResult:
        ws = self.ctx.workspace
        transcript = ws.get("interview_transcript") or ""
        if not transcript.strip():
            return ToolResult(content="需要 interview_transcript（粘贴面试记录到工作区）。", is_error=True)
        prop_id = self.ctx.set_proposal("retrospective", "面试复盘（结构化反馈 + 改进计划）", {
            "transcript": transcript,
            "job_text": ws.get("job_text") or "",
            "company": ws.get("company") or "",
        })
        return ToolResult(content=f"proposal {prop_id} 已创建。")


class RunRetrospectiveTool(Tool):
    name = "run_retrospective"
    description = "执行面试复盘（需 confirm proposal）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"proposal_id": {"type": "string"}},
        "required": ["proposal_id"],
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, proposal_id: str, **_: Any) -> ToolResult:
        prop = self.ctx.consume_proposal(proposal_id)
        if prop is None:
            return ToolResult(content="proposal 未批准。", is_error=True)
        inputs = prop["inputs"]
        result = await self.ctx.services.retrospective.run(
            inputs["transcript"], inputs.get("job_text") or "", inputs.get("company") or "",
            self.ctx.tracer,
        )
        data = result.to_dict()
        art_id = self.ctx.add_artifact("retrospective", data)
        self.ctx.log_activity("retrospective", "面试复盘", artifact_ids=[art_id])
        return ToolResult(content=json.dumps(data, ensure_ascii=False)[:3000])


class GenerateJournalTool(Tool):
    name = "generate_journal"
    description = "生成今日日报或本周周报（无需 confirm）。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "period": {"type": "string", "description": "day | week", "default": "day"},
        },
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, period: str = "day", **_: Any) -> ToolResult:
        period = "week" if period == "week" else "day"
        result = await self.ctx.services.journal.run(self.ctx.tracer, period=period)
        data = result.to_dict() if hasattr(result, "to_dict") else result
        art_id = self.ctx.add_artifact("journal", data)
        self.ctx.log_activity("journal", f"生成{'周报' if period == 'week' else '日报'}", artifact_ids=[art_id])
        md = data.get("markdown", "") if isinstance(data, dict) else ""
        return ToolResult(content=md[:3000] or json.dumps(data, ensure_ascii=False)[:2000])


class ListActivityTool(Tool):
    name = "list_activity"
    description = "列出用户近期求职活动流水（匹配、调研、Gap 等）。用户问「今天做了什么」「上次匹配多少分」时使用。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 20},
            "kind": {"type": "string", "description": "可选过滤：capture_jd, match, gap 等"},
        },
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, limit: int = 20, kind: str = "", **_: Any) -> ToolResult:
        events = self.ctx.services.activity.list_since(
            kind=kind or None, limit=min(limit, 50),
        )
        if not events:
            return ToolResult(content="暂无活动记录。")
        lines = [f"- [{e.get('kind')}] {e.get('summary')}" for e in events[:limit]]
        return ToolResult(content="\n".join(lines))


class ListSystemUpdatesTool(Tool):
    name = "list_system_updates"
    description = "列出系统最近版本更新与功能变更。用户问「有什么新功能」时使用。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 5}},
    }

    def __init__(self, ctx: CopilotContext) -> None:
        self.ctx = ctx

    async def run(self, limit: int = 5, **_: Any) -> ToolResult:
        releases = self.ctx.services.releases.list_releases(limit=min(limit, 10))
        if not releases:
            return ToolResult(content="暂无版本记录。")
        lines = [f"- v{r.get('version')}: {r.get('title')}" for r in releases]
        return ToolResult(content="\n".join(lines))


def build_copilot_tools(ctx: CopilotContext) -> ToolRegistry:
    tools = [
        UpdateWorkspaceTool(ctx),
        RunJDAnalysisTool(ctx),
        ResearchCompanyTool(ctx),
        QuickMatchTool(ctx),
        ProposeMatchTool(ctx),
        RunMatchTool(ctx),
        ProposeRewriteTool(ctx),
        RunRewriteTool(ctx),
        ProposeOutreachTool(ctx),
        RunOutreachTool(ctx),
        ProposeGapTool(ctx),
        RunGapTool(ctx),
        ProposeTechResearchTool(ctx),
        RunTechResearchTool(ctx),
        RunRequirementSynthesisTool(ctx),
        ProposeLearningPlanTool(ctx),
        RunLearningPlanTool(ctx),
        ReviseLearningPlanTool(ctx),
        AssessRoleTool(ctx),
        ProposeMockInterviewTool(ctx),
        RunMockInterviewTool(ctx),
        ProposeRetrospectiveTool(ctx),
        RunRetrospectiveTool(ctx),
        GenerateJournalTool(ctx),
        ListActivityTool(ctx),
        ListSystemUpdatesTool(ctx),
    ]
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg
