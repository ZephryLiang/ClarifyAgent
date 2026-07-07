"""Anti-hallucination faithfulness checks for resume rewriting.

The guardrail is deliberately conservative: a rewrite may only contain numbers
and named entities that are present in the original text, unless they sit inside
an explicit ``[待补充: ...]`` placeholder. Anything else is flagged so the
rewrite can be rejected or downgraded to a placeholder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Numbers, percentages, currency, multipliers like "10x".
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|％|x|X|倍|k|K|w|W|万|亿|ms|s|QPS|TPS|GB|TB|MB)?")
_PLACEHOLDER_RE = re.compile(
    r"\[[^\]]*(?:待补充|待核实|待填|TODO|placeholder)[^\]]*\]", re.IGNORECASE)


@dataclass
class FaithfulnessIssue:
    kind: str  # "unsupported_number" | "unsupported_entity"
    value: str
    note: str = ""


@dataclass
class FaithfulnessReport:
    ok: bool = True
    issues: list[FaithfulnessIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "issues": [{"kind": i.kind, "value": i.value, "note": i.note} for i in self.issues],
        }


def _normalize_number(token: str) -> str:
    return re.sub(r"\s+", "", token).lower()


def _strip_placeholders(text: str) -> str:
    return _PLACEHOLDER_RE.sub(" ", text)


def check_numbers(original: str, rewritten: str) -> list[FaithfulnessIssue]:
    """Flag numeric tokens in ``rewritten`` not present in ``original``."""

    original_numbers = {_normalize_number(t) for t in _NUMBER_RE.findall(original) if t.strip()}
    # Also keep bare digit sequences from the original for looser matching.
    original_digits = set(re.findall(r"\d+", original))

    issues: list[FaithfulnessIssue] = []
    scanned = _strip_placeholders(rewritten)
    for token in _NUMBER_RE.findall(scanned):
        token = token.strip()
        if not token or not any(ch.isdigit() for ch in token):
            continue
        norm = _normalize_number(token)
        digits = "".join(ch for ch in token if ch.isdigit())
        if norm in original_numbers or digits in original_digits:
            continue
        issues.append(FaithfulnessIssue(
            kind="unsupported_number",
            value=token,
            note="改写中出现原文没有的数字，可能是幻觉；请核实或改为占位符。",
        ))
    return issues


def verify_faithfulness(original: str, rewritten: str) -> FaithfulnessReport:
    """Return a report; ``ok`` is False when any unsupported claim is found."""

    issues = check_numbers(original, rewritten)
    return FaithfulnessReport(ok=not issues, issues=issues)


def repair(rewritten: str, report: FaithfulnessReport) -> str:
    """Deterministically neutralise unsupported claims by placeholdering them.

    Each flagged numeric value is wrapped as ``[待核实: X]`` so the rewrite no
    longer asserts a fabricated figure — turning a hallucination into an honest
    prompt for the candidate to confirm. Re-verifying the result passes.
    """

    fixed = rewritten
    for issue in report.issues:
        if issue.kind == "unsupported_number" and issue.value in fixed:
            fixed = fixed.replace(issue.value, f"[待核实: {issue.value}]", 1)
    return fixed
