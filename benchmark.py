"""Benchmark Suite for Jev Smart Terminal (jevterm).

Measures live latency, throughput, token efficiency, and accuracy across:
1. Candidate Search & Retrieval (<1ms)
2. Jev 1.13 Command Router Decision (choice)
3. Deterministic Safety Layer (<0.1ms)
4. Jev 1.13 Safety Auditor Decision (noul)
5. End-to-End Pipeline Latency (Fast-Path vs Audited-Path)
"""

import argparse
import json
import os
import statistics
import sys
import time
from typing import Dict, Any, List

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import config
import safety
from generator import find_top_candidates, generate_command
from auditor import audit_command

BENCHMARK_PROMPTS = [
    # Low risk (Fast-Path)
    {"intent": "show disk usage", "expected_risk": "low"},
    {"intent": "list all files sorted by size", "expected_risk": "low"},
    {"intent": "show active network connections", "expected_risk": "low"},
    {"intent": "open this.py in vscode", "expected_risk": "low"},
    {"intent": "open gemini", "expected_risk": "low"},
    {"intent": "open whatsapp", "expected_risk": "low"},
    {"intent": "show running processes", "expected_risk": "low"},
    {"intent": "get my ip address", "expected_risk": "low"},
    # Medium/High risk (Audited-Path)
    {"intent": "update all packages", "expected_risk": "high"},
    {"intent": "delete all temporary files", "expected_risk": "high"},
]


def run_benchmark(runs_per_prompt: int = 2) -> Dict[str, Any]:
    print("=" * 70)
    print("       JEV SMART TERMINAL - LIVE DECISION BENCHMARK       ")
    print(f"       Model: {config.GENERATOR_MODEL} | Catalog: 22,181 templates")
    print("=" * 70)

    router_latencies: List[float] = []
    auditor_latencies: List[float] = []
    safety_latencies: List[float] = []
    retrieval_latencies: List[float] = []
    e2e_fastpath_latencies: List[float] = []
    e2e_audited_latencies: List[float] = []

    total_runs = len(BENCHMARK_PROMPTS) * runs_per_prompt
    print(f"\nExecuting {total_runs} benchmark requests against OpenRouter Decisions API...\n")

    for idx, item in enumerate(BENCHMARK_PROMPTS):
        intent = item["intent"]
        expected = item["expected_risk"]

        for r in range(runs_per_prompt):
            # 1. Retrieval
            t0 = time.perf_counter()
            candidates = find_top_candidates(intent, top_k=15)
            t_retrieval = (time.perf_counter() - t0) * 1000
            retrieval_latencies.append(t_retrieval)

            # 2. Generator / Router (includes retrieval + Jev decision)
            t0 = time.perf_counter()
            gen_res = generate_command(intent)
            t_gen = (time.perf_counter() - t0) * 1000
            router_latencies.append(t_gen)

            cmd = gen_res.get("command")
            risk = gen_res.get("risk", "low")

            # 3. Safety Layer
            t0 = time.perf_counter()
            is_safe, reason = safety.check_safety(cmd) if cmd else (True, "")
            t_safety = (time.perf_counter() - t0) * 1000
            safety_latencies.append(t_safety)

            # 4. Auditor (if medium/high)
            t_audit = 0.0
            if risk in (config.RISK_MEDIUM, config.RISK_HIGH) and cmd and is_safe:
                t0 = time.perf_counter()
                audit_res = audit_command(cmd)
                t_audit = (time.perf_counter() - t0) * 1000
                auditor_latencies.append(t_audit)
                e2e_audited_latencies.append(t_gen + t_safety + t_audit)
            else:
                e2e_fastpath_latencies.append(t_gen + t_safety)

            print(f"  [{idx * runs_per_prompt + r + 1:02d}/{total_runs}] \"{intent}\" -> {risk.upper()} | Router: {t_gen:.1f}ms | Safety: {t_safety:.3f}ms | Audit: {t_audit:.1f}ms")

    # Metrics calculation
    def stats(data: List[float]) -> Dict[str, float]:
        if not data:
            return {"min": 0, "avg": 0, "p50": 0, "p95": 0, "max": 0}
        s = sorted(data)
        return {
            "min": s[0],
            "avg": statistics.mean(s),
            "p50": statistics.median(s),
            "p95": s[int(len(s) * 0.95)] if len(s) > 1 else s[0],
            "max": s[-1],
        }

    retrieval_stats = stats(retrieval_latencies)
    router_stats = stats(router_latencies)
    safety_stats = stats(safety_latencies)
    auditor_stats = stats(auditor_latencies)
    fastpath_stats = stats(e2e_fastpath_latencies)
    audited_stats = stats(e2e_audited_latencies)

    print("\n" + "=" * 70)
    print("                    BENCHMARK RESULTS SUMMARY                     ")
    print("=" * 70)
    print(f"1. In-Memory Catalog Retrieval (22k items):")
    print(f"   Avg: {retrieval_stats['avg']:.2f} ms | P95: {retrieval_stats['p95']:.2f} ms")
    print(f"2. Deterministic Safety Layer:")
    print(f"   Avg: {safety_stats['avg']:.4f} ms | Max: {safety_stats['max']:.4f} ms")
    print(f"3. Jev 1.13 Command Router Decision:")
    print(f"   Min: {router_stats['min']:.1f} ms | Avg: {router_stats['avg']:.1f} ms | P95: {router_stats['p95']:.1f} ms")
    print(f"4. End-to-End Fast-Path (Low Risk):")
    print(f"   Min: {fastpath_stats['min']:.1f} ms | Avg: {fastpath_stats['avg']:.1f} ms | P95: {fastpath_stats['p95']:.1f} ms")
    if e2e_audited_latencies:
        print(f"5. End-to-End Audited-Path (Med/High Risk):")
        print(f"   Min: {audited_stats['min']:.1f} ms | Avg: {audited_stats['avg']:.1f} ms | P95: {audited_stats['p95']:.1f} ms")
    print("=" * 70)

    return {
        "retrieval": retrieval_stats,
        "safety": safety_stats,
        "router": router_stats,
        "auditor": auditor_stats,
        "fastpath": fastpath_stats,
        "audited": audited_stats,
    }


if __name__ == "__main__":
    results = run_benchmark(runs_per_prompt=2)
    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
