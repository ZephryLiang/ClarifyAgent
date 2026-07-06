"""The agent tool-calling loop.

An :class:`Agent` drives a conversation with the LLM gateway: it sends the
messages + tool specs, and whenever the model asks to call tools it executes
them (via the :class:`ToolRegistry`), appends the results, and loops — until the
model produces a final answer or the iteration budget is exhausted.

Every LLM call and tool invocation is recorded on the :class:`Tracer`, giving
full observability into the agent's reasoning steps.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..config import settings as default_settings
from ..gateway.base import Message, ToolCall
from ..gateway.registry import Gateway
from .tools import ToolRegistry, ToolResult
from .trace import SpanKind, SpanStatus, Tracer


@dataclass
class AgentResult:
    output: str
    messages: list[Message] = field(default_factory=list)
    iterations: int = 0
    tool_calls: int = 0
    stopped_reason: str = "completed"


class Agent:
    """A single tool-using agent."""

    def __init__(
        self,
        gateway: Gateway,
        tools: ToolRegistry | None = None,
        tracer: Tracer | None = None,
        system: str = "",
        name: str = "agent",
        max_iterations: int | None = None,
        temperature: float = 0.4,
        prefer_provider: str | None = None,
        parent_span_id: str | None = None,
        approver: Any = None,
        context_manager: Any = None,
    ) -> None:
        self.gateway = gateway
        self.tools = tools or ToolRegistry()
        self.tracer = tracer or Tracer()
        self.system = system
        self.name = name
        self.max_iterations = max_iterations or default_settings.max_tool_iterations
        self.temperature = temperature
        self.prefer_provider = prefer_provider
        self.parent_span_id = parent_span_id
        # Optional governance approver (HITL) and context compactor. Kept as
        # ``Any`` to avoid import cycles; duck-typed at call sites.
        self.approver = approver
        if context_manager is None:
            from .context import ContextManager

            context_manager = ContextManager(
                char_budget=default_settings.context_char_budget,
                keep_recent=default_settings.context_keep_recent,
            )
        self.context_manager = context_manager

    async def run(self, prompt: str, history: list[Message] | None = None) -> AgentResult:
        messages: list[Message] = list(history or [])
        messages.append(Message(role="user", content=prompt))

        agent_span = self.tracer.start_span(self.name, SpanKind.AGENT, self.parent_span_id,
                                            prompt=_truncate(prompt))
        tool_specs = self.tools.specs()
        total_tool_calls = 0

        try:
            for iteration in range(1, self.max_iterations + 1):
                if self.context_manager is not None:
                    messages, compacted = self.context_manager.fit(messages)
                    if compacted:
                        self.tracer.log("context compacted to fit budget",
                                        size=self.context_manager.size(messages))
                response = await self._call_llm(messages, tool_specs, agent_span.id)

                if not response.wants_tools:
                    self.tracer.end_span(agent_span, SpanStatus.OK,
                                         iterations=iteration, output=_truncate(response.content))
                    return AgentResult(output=response.content, messages=messages,
                                       iterations=iteration, tool_calls=total_tool_calls)

                # Record the assistant's tool-call turn.
                messages.append(Message(role="assistant", content=response.content,
                                        tool_calls=response.tool_calls))

                # Execute all requested tool calls (in parallel).
                results = await self._execute_tools(response.tool_calls, agent_span.id)
                total_tool_calls += len(results)
                for call, result in zip(response.tool_calls, results, strict=False):
                    messages.append(Message(role="tool", tool_call_id=call.id,
                                            name=call.name, content=result.content))

            self.tracer.end_span(agent_span, SpanStatus.OK, iterations=self.max_iterations,
                                 stopped="max_iterations")
            final = messages[-1].content if messages else ""
            return AgentResult(output=final, messages=messages, iterations=self.max_iterations,
                               tool_calls=total_tool_calls, stopped_reason="max_iterations")
        except Exception as exc:  # noqa: BLE001
            self.tracer.end_span(agent_span, SpanStatus.ERROR, error=str(exc))
            raise

    async def _call_llm(self, messages, tool_specs, parent_id):
        span = self.tracer.start_span(f"llm:{self.prefer_provider or 'auto'}", SpanKind.LLM,
                                      parent_id, message_count=len(messages))

        def on_attempt(provider_name: str, error: Exception | None) -> None:
            self.tracer.log(f"llm attempt via {provider_name}"
                            + (f" failed: {error}" if error else " ok"),
                            provider=provider_name, ok=error is None)

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: self.gateway.chat(
                    messages=messages,
                    tools=tool_specs or None,
                    temperature=self.temperature,
                    system=self.system,
                    prefer=self.prefer_provider,
                    on_attempt=on_attempt,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self.tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            raise

        self.tracer.end_span(span, SpanStatus.OK, tokens=response.usage.total_tokens,
                             provider=response.provider, model=response.model,
                             tool_calls=[tc.name for tc in response.tool_calls])
        return response

    async def _execute_tools(self, calls: list[ToolCall], parent_id: str) -> list[ToolResult]:
        async def run_one(call: ToolCall) -> ToolResult:
            span = self.tracer.start_span(f"tool:{call.name}", SpanKind.TOOL, parent_id,
                                          arguments=call.arguments)
            tool = self.tools.get(call.name)
            if tool is None:
                self.tracer.end_span(span, SpanStatus.ERROR, error="unknown tool")
                return ToolResult(content=f"错误: 未知工具 '{call.name}'", is_error=True)
            # Governance gate for side-effecting tools (HITL / audit).
            if getattr(tool, "side_effect", False) and self.approver is not None:
                decision = self.approver.check(call.name, call.arguments,
                                               actor=self.name, trace_id=self.tracer.trace_id)
                if not decision.allowed:
                    self.tracer.end_span(span, SpanStatus.OK, blocked=True,
                                         decision=decision.decision)
                    return ToolResult(content=f"[需人工确认] {decision.reason}", is_error=False)
            try:
                result = await tool.run(**call.arguments)
                self.tracer.end_span(span, SpanStatus.OK if not result.is_error else SpanStatus.ERROR,
                                     output=_truncate(result.content),
                                     error=result.content if result.is_error else None)
                return result
            except Exception as exc:  # noqa: BLE001
                self.tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
                return ToolResult(content=f"工具执行失败: {exc}", is_error=True)

        return list(await asyncio.gather(*(run_one(c) for c in calls)))


def _truncate(text: str, limit: int = 500) -> str:
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…"
