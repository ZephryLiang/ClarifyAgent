"""Trace attribution analysis (Observability layer).

Given a trace (a list of spans with parent/child links, durations, tokens and
status), attribute:

* **Latency** — each span's *self time* (its own duration minus that of its
  direct children), so a slow parent isn't double-counted; ranked top offenders.
* **Cost** — token totals by provider and by span kind.
* **Failure** — the root-cause span (the earliest-starting error span with no
  errored ancestor), the error chain, and which ETCLOVG layer it maps to.

Pure functions over the serialized trace dict produced by ``Tracer.summary()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Map span kinds onto ETCLOVG layers for failure attribution.
_KIND_TO_LAYER = {
    "llm": "Gateway/Lifecycle",
    "tool": "Tooling",
    "mcp": "Tooling(MCP)",
    "subagent": "Lifecycle",
    "agent": "Lifecycle",
    "retrieval": "Context/Verification",
}


@dataclass
class AttributionReport:
    trace_id: str = ""
    total_duration_ms: float = 0.0
    total_tokens: int = 0
    self_time_by_kind: dict[str, float] = field(default_factory=dict)
    tokens_by_provider: dict[str, int] = field(default_factory=dict)
    top_spans: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    root_cause: dict[str, Any] | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "self_time_by_kind": self.self_time_by_kind,
            "tokens_by_provider": self.tokens_by_provider,
            "top_spans": self.top_spans,
            "errors": self.errors,
            "root_cause": self.root_cause,
            "summary": self.summary,
        }


def analyze_trace(trace: dict[str, Any]) -> AttributionReport:
    spans: list[dict[str, Any]] = trace.get("spans", []) if trace else []
    report = AttributionReport(trace_id=trace.get("trace_id", "") if trace else "")
    if not spans:
        report.summary = "空轨迹，无可归因数据。"
        return report

    by_id = {s["id"]: s for s in spans}
    children: dict[str, list[dict[str, Any]]] = {}
    for s in spans:
        if s.get("parent_id"):
            children.setdefault(s["parent_id"], []).append(s)

    # -- latency: self time per span --------------------------------------- #
    self_by_kind: dict[str, float] = {}
    span_self: list[dict[str, Any]] = []
    for s in spans:
        dur = s.get("duration_ms") or 0.0
        child_dur = sum((c.get("duration_ms") or 0.0) for c in children.get(s["id"], []))
        self_ms = max(0.0, dur - child_dur)
        self_by_kind[s["kind"]] = round(self_by_kind.get(s["kind"], 0.0) + self_ms, 1)
        span_self.append({"name": s["name"], "kind": s["kind"], "self_ms": round(self_ms, 1),
                          "duration_ms": round(dur, 1), "tokens": s.get("tokens", 0),
                          "provider": s.get("attributes", {}).get("provider")})
    span_self.sort(key=lambda x: x["self_ms"], reverse=True)

    # -- cost: tokens by provider ------------------------------------------ #
    tokens_by_provider: dict[str, int] = {}
    for s in spans:
        tok = s.get("tokens", 0) or 0
        if tok:
            prov = s.get("attributes", {}).get("provider") or "unknown"
            tokens_by_provider[prov] = tokens_by_provider.get(prov, 0) + tok

    # -- failure: root cause ----------------------------------------------- #
    error_spans = [s for s in spans if s.get("status") == "error"]

    def has_errored_ancestor(s: dict[str, Any]) -> bool:
        pid = s.get("parent_id")
        seen = set()
        while pid and pid in by_id and pid not in seen:
            seen.add(pid)
            if by_id[pid].get("status") == "error":
                return True
            pid = by_id[pid].get("parent_id")
        return False

    roots = [s for s in error_spans if not has_errored_ancestor(s)]
    roots.sort(key=lambda s: s.get("start_ms", 0))
    errors = [{"name": s["name"], "kind": s["kind"], "layer": _KIND_TO_LAYER.get(s["kind"], "?"),
               "error": s.get("error")} for s in error_spans]
    root_cause = None
    if roots:
        r = roots[0]
        root_cause = {"name": r["name"], "kind": r["kind"],
                      "layer": _KIND_TO_LAYER.get(r["kind"], "?"), "error": r.get("error")}

    report.total_duration_ms = round(trace.get("duration_ms", 0.0), 1)
    report.total_tokens = trace.get("total_tokens", 0)
    report.self_time_by_kind = dict(sorted(self_by_kind.items(), key=lambda x: x[1], reverse=True))
    report.tokens_by_provider = tokens_by_provider
    report.top_spans = span_self[:5]
    report.errors = errors
    report.root_cause = root_cause
    report.summary = _summarize(report)
    return report


def _summarize(r: AttributionReport) -> str:
    parts: list[str] = []
    if r.top_spans:
        top = r.top_spans[0]
        parts.append(f"耗时主要来自 {top['kind']}「{top['name']}」(自耗时 {top['self_ms']}ms)。")
    if r.tokens_by_provider:
        prov = max(r.tokens_by_provider.items(), key=lambda x: x[1])
        parts.append(f"token 主要消耗在 provider={prov[0]} ({prov[1]} tok)。")
    if r.root_cause:
        parts.append(f"失败根因: {r.root_cause['layer']} 层「{r.root_cause['name']}」— {r.root_cause['error']}。")
    elif not r.errors:
        parts.append("无错误 span，轨迹健康。")
    return " ".join(parts)
