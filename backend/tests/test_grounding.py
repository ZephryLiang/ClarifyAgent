"""Tests for the anti-hallucination faithfulness checks."""

from app.modules.grounding import verify_faithfulness


def test_flags_fabricated_numbers():
    report = verify_faithfulness("提升了系统性能", "将延迟从 800ms 降到 200ms")
    assert not report.ok
    values = {i.value for i in report.issues}
    assert any("800" in v for v in values)


def test_allows_numbers_present_in_original():
    report = verify_faithfulness("QPS 从 2k 提升到 15k", "将 QPS 从 2k 提升到 15k，性能显著改善")
    assert report.ok


def test_placeholder_numbers_are_ignored():
    report = verify_faithfulness("负责订单系统", "重构订单系统，提升 [待补充: 例如 30%] 吞吐")
    assert report.ok


def test_no_numbers_is_ok():
    report = verify_faithfulness("参与项目", "主导项目并推动落地")
    assert report.ok
