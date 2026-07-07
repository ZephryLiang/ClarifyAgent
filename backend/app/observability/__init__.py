"""Observability analytics: trace attribution (latency / cost / failure)."""

from .attribution import AttributionReport, analyze_trace

__all__ = ["AttributionReport", "analyze_trace"]
