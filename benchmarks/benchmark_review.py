"""Repeatable latency benchmark for short, medium, and full-length drafts."""
from __future__ import annotations
import statistics, time
from academic_analyser import AcademicAnalyzer
from advanced_humanize import AdvancedHumanizer

SAMPLES = {"short": "Caste shapes land relations. This remains underexplored.", "medium": "Caste shapes land relations. " * 40, "full": "Caste shapes land relations. This remains underexplored. " * 400}
def run(rounds=3):
    analyzer, editor = AcademicAnalyzer(), AdvancedHumanizer()
    for name, text in SAMPLES.items():
        times=[]
        for _ in range(rounds):
            start=time.perf_counter(); editor.humanize(text); analyzer.analyse(text); times.append((time.perf_counter()-start)*1000)
        print(f"{name}: median={statistics.median(times):.2f}ms p95={sorted(times)[min(len(times)-1, int(len(times)*.95))]:.2f}ms chars={len(text)}")
if __name__ == "__main__": run()
