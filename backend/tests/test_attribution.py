"""Tests for trace attribution analysis (Observability)."""

from app.observability import analyze_trace


def _trace():
    return {
        "trace_id": "t1",
        "duration_ms": 1000.0,
        "total_tokens": 300,
        "spans": [
            {"id": "a", "parent_id": None, "name": "agent", "kind": "agent",
             "status": "ok", "start_ms": 0, "duration_ms": 1000.0, "tokens": 0, "attributes": {}},
            {"id": "b", "parent_id": "a", "name": "llm:openai", "kind": "llm",
             "status": "ok", "start_ms": 10, "duration_ms": 700.0, "tokens": 300,
             "attributes": {"provider": "openai"}},
            {"id": "c", "parent_id": "a", "name": "tool:web_search", "kind": "tool",
             "status": "error", "start_ms": 720, "duration_ms": 100.0, "tokens": 0,
             "error": "timeout", "attributes": {}},
        ],
    }


def test_self_time_excludes_children():
    r = analyze_trace(_trace())
    # agent self time = 1000 - (700 + 100) = 200
    assert r.self_time_by_kind["agent"] == 200.0
    assert r.self_time_by_kind["llm"] == 700.0


def test_tokens_attributed_to_provider():
    r = analyze_trace(_trace())
    assert r.tokens_by_provider == {"openai": 300}


def test_root_cause_is_error_span_with_layer():
    r = analyze_trace(_trace())
    assert r.root_cause is not None
    assert r.root_cause["name"] == "tool:web_search"
    assert r.root_cause["layer"] == "Tooling"
    assert "timeout" in r.summary


def test_empty_trace():
    r = analyze_trace({"trace_id": "x", "spans": []})
    assert "空轨迹" in r.summary
