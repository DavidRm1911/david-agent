"""Runs the same prompt against multiple registered providers and reports
objective, measured metrics — latency, tokens, cost, success/failure.

Deliberately does not score "quality": CLAUDE.md §26 says never invent
results, and there is no real judge (human or LLM) wired in. Latency, token
counts, and cost are the numbers this can actually measure honestly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from david_agent.models.base import ModelMessage
from david_agent.models.registry import ModelRegistry


@dataclass
class BenchmarkResult:
    model_name: str
    latency_s: float
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    text: str | None
    error: str | None


def run_benchmark(registry: ModelRegistry, prompt: str, *, model_names: list[str] | None = None) -> list[BenchmarkResult]:
    names = model_names or registry.names()
    results: list[BenchmarkResult] = []
    for name in names:
        provider = registry.get(name)
        start = time.monotonic()
        try:
            response = provider.complete([ModelMessage(role="user", content=prompt)])
            results.append(
                BenchmarkResult(
                    model_name=name,
                    latency_s=time.monotonic() - start,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cost_usd=response.cost_usd,
                    text=response.text,
                    error=None,
                )
            )
        except Exception as e:  # noqa: BLE001 — one model's failure shouldn't stop the rest of the benchmark
            results.append(
                BenchmarkResult(
                    model_name=name,
                    latency_s=time.monotonic() - start,
                    input_tokens=None,
                    output_tokens=None,
                    cost_usd=None,
                    text=None,
                    error=str(e),
                )
            )
    return results
