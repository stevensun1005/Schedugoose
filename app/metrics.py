"""Lightweight in-process metrics + structured logging for the API.

Tracks request counts, latency, and GenAI-model signals (LLM usage vs rule-based
fallback, RAG backend) so the service's behaviour is observable — the minimum an
MLOps setup needs before wiring Prometheus/Grafana or CloudWatch. Exposed at
``/metrics`` (JSON) and, when ``prometheus_client`` is installed, in Prometheus
text format.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from contextlib import contextmanager
from typing import Any, Iterator


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.counters: Counter[str] = Counter()
        self.latency_ms_sum = 0.0
        self.latency_count = 0
        self.latency_max_ms = 0.0
        self.rag_sources: Counter[str] = Counter()
        self.started_at = time.time()

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] += n

    def observe_latency(self, ms: float) -> None:
        with self._lock:
            self.latency_ms_sum += ms
            self.latency_count += 1
            self.latency_max_ms = max(self.latency_max_ms, ms)

    def record_turn(self, *, used_llm: bool, llm_parse_failed: bool, rag_source: str | None) -> None:
        self.incr("plan_requests_total")
        self.incr("llm_calls_total" if used_llm else "rule_based_turns_total")
        if llm_parse_failed:
            self.incr("llm_fallbacks_total")
        if rag_source:
            with self._lock:
                self.rag_sources[rag_source] += 1

    @contextmanager
    def timer(self) -> Iterator[None]:
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.observe_latency((time.perf_counter() - t0) * 1000)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg = self.latency_ms_sum / self.latency_count if self.latency_count else 0.0
            total = self.counters.get("plan_requests_total", 0)
            llm = self.counters.get("llm_calls_total", 0)
            return {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "counters": dict(self.counters),
                "latency_ms": {
                    "avg": round(avg, 1),
                    "max": round(self.latency_max_ms, 1),
                    "count": self.latency_count,
                },
                "llm_usage_rate": round(llm / total, 3) if total else 0.0,
                "rag_sources": dict(self.rag_sources),
            }

    def prometheus(self) -> str:
        snap = self.snapshot()
        lines = [
            "# HELP schedugoose_up 1 if the service is running",
            "# TYPE schedugoose_up gauge",
            "schedugoose_up 1",
        ]
        for name, val in snap["counters"].items():
            lines.append(f"# TYPE schedugoose_{name} counter")
            lines.append(f"schedugoose_{name} {val}")
        lines.append(f"schedugoose_latency_ms_avg {snap['latency_ms']['avg']}")
        lines.append(f"schedugoose_latency_ms_max {snap['latency_ms']['max']}")
        lines.append(f"schedugoose_llm_usage_rate {snap['llm_usage_rate']}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()
