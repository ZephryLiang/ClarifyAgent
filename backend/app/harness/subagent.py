"""Parallel subagent orchestration.

Some tasks decompose naturally into independent investigations that can run
concurrently — e.g. for job matching we simultaneously analyse the JD, analyse
the resume, and research the company. The :class:`Orchestrator` spawns such
subagents with ``asyncio.gather`` and records each under its own trace span.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..gateway.registry import Gateway
from .agent import Agent, AgentResult
from .tools import ToolRegistry
from .trace import SpanKind, SpanStatus, Tracer


@dataclass
class SubagentTask:
    name: str
    prompt: str
    system: str = ""
    tool_names: list[str] | None = None  # None => all tools; [] => no tools
    temperature: float = 0.3


@dataclass
class SubagentOutcome:
    name: str
    output: str
    ok: bool = True
    error: str | None = None


class Orchestrator:
    """Runs subagents in parallel under a shared tracer."""

    def __init__(self, gateway: Gateway, tools: ToolRegistry, tracer: Tracer | None = None,
                 max_iterations: int = 5) -> None:
        self.gateway = gateway
        self.tools = tools
        self.tracer = tracer or Tracer()
        self.max_iterations = max_iterations

    async def run_parallel(self, tasks: list[SubagentTask],
                           parent_span_id: str | None = None) -> list[SubagentOutcome]:
        group = self.tracer.start_span("parallel-subagents", SpanKind.AGENT, parent_span_id,
                                       count=len(tasks), tasks=[t.name for t in tasks])

        async def run_task(task: SubagentTask) -> SubagentOutcome:
            span = self.tracer.start_span(f"subagent:{task.name}", SpanKind.SUBAGENT, group.id)
            tools = self.tools if task.tool_names is None else self.tools.subset(task.tool_names)
            agent = Agent(
                gateway=self.gateway,
                tools=tools,
                tracer=self.tracer,
                system=task.system,
                name=f"subagent:{task.name}",
                max_iterations=self.max_iterations,
                temperature=task.temperature,
                parent_span_id=span.id,
            )
            try:
                result: AgentResult = await agent.run(task.prompt)
                self.tracer.end_span(span, SpanStatus.OK, output_len=len(result.output))
                return SubagentOutcome(name=task.name, output=result.output, ok=True)
            except Exception as exc:  # noqa: BLE001
                self.tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
                return SubagentOutcome(name=task.name, output="", ok=False, error=str(exc))

        outcomes = list(await asyncio.gather(*(run_task(t) for t in tasks)))
        self.tracer.end_span(group, SpanStatus.OK,
                             ok_count=sum(1 for o in outcomes if o.ok))
        return outcomes
