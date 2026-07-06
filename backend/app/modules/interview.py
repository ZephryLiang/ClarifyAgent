"""Module ④: multi-turn mock interview (中英文).

An :class:`InterviewSession` holds the running transcript. The interviewer agent
asks one question at a time, adapts follow-ups to the candidate's answers, and
scores the JD's required skills. Sessions are serialisable so the API/storage
layer can persist and resume them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..domain import parse_job_text, parse_resume_text
from ..gateway.base import Message
from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import llm_available

_SYSTEM = """你是资深技术面试官，正在对候选人进行模拟面试。规则：
- 每次只问一个问题，围绕岗位JD的核心要求，结合候选人简历。
- 根据候选人的上一轮回答做有针对性的追问；由浅入深。
- 语言与岗位JD一致（中文或英文，外企用英文）。
- 只输出面试官这一轮要说的话（问题或简短点评+下一个问题），不要输出旁白或元信息。"""


@dataclass
class InterviewTurn:
    role: str  # "interviewer" | "candidate"
    content: str


@dataclass
class InterviewSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    resume_text: str = ""
    job_text: str = ""
    language: str = "zh"
    turns: List[InterviewTurn] = field(default_factory=list)
    finished: bool = False
    max_questions: int = 6

    @property
    def question_count(self) -> int:
        return sum(1 for t in self.turns if t.role == "interviewer")

    def transcript(self) -> str:
        label = {"interviewer": "面试官", "candidate": "候选人"}
        return "\n".join(f"{label[t.role]}: {t.content}" for t in self.turns)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "language": self.language,
            "finished": self.finished,
            "question_count": self.question_count,
            "max_questions": self.max_questions,
            "turns": [{"role": t.role, "content": t.content} for t in self.turns],
        }


class MockInterviewer:
    def __init__(self, gateway: Optional[Gateway] = None) -> None:
        self.gateway = gateway
        self._sessions: Dict[str, InterviewSession] = {}

    def get(self, session_id: str) -> Optional[InterviewSession]:
        return self._sessions.get(session_id)

    def create(self, resume_text: str, job_text: str, language: str = "zh",
               max_questions: int = 6) -> InterviewSession:
        session = InterviewSession(resume_text=resume_text, job_text=job_text,
                                   language=language, max_questions=max_questions)
        self._sessions[session.id] = session
        return session

    async def ask_next(self, session: InterviewSession, tracer: Optional[Tracer] = None) -> str:
        """Produce the next interviewer question and append it to the session."""

        tracer = tracer or Tracer()
        span = tracer.start_span("interview-ask", SpanKind.AGENT,
                                 q=session.question_count, has_llm=llm_available(self.gateway))
        try:
            if session.question_count >= session.max_questions:
                session.finished = True
                closing = "面试到此结束，感谢你的时间。稍后可以查看面试复盘。"
                session.turns.append(InterviewTurn("interviewer", closing))
                tracer.end_span(span, SpanStatus.OK, finished=True)
                return closing

            if llm_available(self.gateway):
                question = await self._ask_llm(session, tracer, span.id)
            else:
                question = self._ask_offline(session)
            session.turns.append(InterviewTurn("interviewer", question))
            tracer.end_span(span, SpanStatus.OK)
            return question
        except Exception as exc:  # noqa: BLE001
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            raise

    def answer(self, session: InterviewSession, answer: str) -> None:
        session.turns.append(InterviewTurn("candidate", answer))

    async def _ask_llm(self, session: InterviewSession, tracer: Tracer, parent_id: str) -> str:
        agent = Agent(self.gateway, ToolRegistry(), tracer, system=_SYSTEM,
                      name="interviewer", temperature=0.6, parent_span_id=parent_id)
        history: List[Message] = []
        for t in session.turns:
            role = "assistant" if t.role == "interviewer" else "user"
            history.append(Message(role=role, content=t.content))
        if not session.turns:
            prompt = (f"岗位JD：\n{session.job_text}\n\n候选人简历：\n{session.resume_text}\n\n"
                      "请开始面试，先做一句简短开场并提出第一个问题。")
        else:
            prompt = "请根据候选人的回答给出下一轮（可含简短点评）的问题。"
        result = await agent.run(prompt, history=history)
        return result.output.strip()

    def _ask_offline(self, session: InterviewSession) -> str:
        resume = parse_resume_text(session.resume_text)
        job = parse_job_text(session.job_text)
        idx = session.question_count
        bank: List[str] = [
            f"请先做个自我介绍，并说明你为什么适合「{job.title or '这个岗位'}」？",
        ]
        for skill in (job.required_skills or resume.skills)[:3]:
            bank.append(f"能否详细讲讲你在 {skill} 方面的实战经验，遇到过什么难点？")
        for resp in job.responsibilities[:2]:
            bank.append(f"针对「{resp[:36]}」这类职责，你会如何着手？")
        bank.append("你遇到过最大的技术挑战是什么？如何解决的？")
        if idx < len(bank):
            return bank[idx]
        return "还有什么想补充或想了解我们团队的吗？"
