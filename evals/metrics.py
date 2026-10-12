import json
import statistics
from dataclasses import dataclass


@dataclass
class RowResult:
    id: str
    type: str
    status_ok: bool
    citation_recall: float | None
    tools_ok: bool
    leaks: list[str]
    latency_ms: int
    tokens: int
    cost_usd: float


def citation_recall(expected: list[str], got: list[str]) -> float | None:
    if not expected:
        return None
    return sum(ref in got for ref in expected) / len(expected)


def tools_match(expected: list[str], traces: list[dict]) -> bool:
    called = {call["tool"] for t in traces for call in t.get("data", {}).get("tool_calls", [])}
    return called == set(expected)


def find_leaks(forbidden: list[str], answer: dict | None, traces: list[dict]) -> list[str]:
    # Only text carries a value: a trace's token and cost counters can contain any digits.
    payloads = [{"node": trace["node"], "data": trace["data"]} for trace in traces]
    haystack = (json.dumps(answer, ensure_ascii=False) + json.dumps(payloads, ensure_ascii=False)).lower()
    return [value for value in forbidden if value.lower() in haystack]


def summarize(rows: list[RowResult]) -> dict:
    recalls = [r.citation_recall for r in rows if r.citation_recall is not None]
    latencies = sorted(r.latency_ms for r in rows)
    return {
        "rows": len(rows),
        "status_accuracy": sum(r.status_ok for r in rows) / len(rows),
        "citation_recall": statistics.mean(recalls) if recalls else None,
        "tool_accuracy": sum(r.tools_ok for r in rows) / len(rows),
        "leak_count": sum(len(r.leaks) for r in rows),
        "latency_p50_ms": latencies[(len(latencies) - 1) // 2],
        "latency_p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
        "avg_tokens": statistics.mean(r.tokens for r in rows),
        "total_cost_usd": sum(r.cost_usd for r in rows),
    }
