"""求职 Agent backend package.

An agentic job-seeking assistant with:

* a dual-protocol LLM gateway (OpenAI-compatible + Anthropic native),
* an agent harness (tool-calling loop, parallel subagents, observability),
* an MCP client so external job-platform servers plug in as tools,
* agentic search over a grounded resume best-practice knowledge base.
"""

__version__ = "0.1.0"
