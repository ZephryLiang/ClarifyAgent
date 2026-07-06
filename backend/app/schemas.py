"""Pydantic request/response schemas for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RewriteRequest(BaseModel):
    resume_text: str = Field(..., description="简历纯文本")
    job_text: str | None = Field(None, description="目标岗位 JD（可选，用于对齐关键词）")
    stream: bool = Field(False, description="是否以 SSE 流式返回 agent 执行过程")


class MatchRequest(BaseModel):
    resume_text: str
    job_text: str
    stream: bool = False


class OutreachRequest(BaseModel):
    resume_text: str
    job_text: str
    style: str = Field("professional", description="professional | warm | concise")
    stream: bool = False


class InterviewStartRequest(BaseModel):
    resume_text: str
    job_text: str
    language: str = Field("zh", description="zh | en")
    max_questions: int = 6


class InterviewAnswerRequest(BaseModel):
    session_id: str
    answer: str


class RetrospectiveRequest(BaseModel):
    transcript: str | None = Field(None, description="面试记录文本")
    session_id: str | None = Field(None, description="或提供模拟面试的 session_id")
    job_text: str = ""
    company: str = ""
    stream: bool = False


class MemoryCreateRequest(BaseModel):
    content: str
    kind: str = Field("insight", description="insight | principle | preference | fact | recurring")
    tags: list[str] = Field(default_factory=list)


class MemoryUpdateRequest(BaseModel):
    content: str
    tags: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    title: str
    content: str
    subdir: str = "求职Agent"
    tags: list[str] = Field(default_factory=list)
