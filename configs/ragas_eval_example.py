"""Minimal Ragas evaluation structure for v0.1 RAG cases.

The example builds a tiny dataset from llm_cases.jsonl and uses expected answers
as offline mock responses. If Ragas is missing, it prints a clear install hint
instead of failing at import time.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CASES_PATH = Path(__file__).resolve().parents[1] / "cases" / "llm_cases.jsonl"


def load_rag_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with CASES_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            case = json.loads(line)
            if case.get("task_type") == "rag_qa":
                cases.append(case)
    return cases


def build_ragas_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in load_rag_cases():
        expected = case["expected"]
        rows.append(
            {
                "question": case["input"],
                "answer": expected["answer"],
                "contexts": case["context"],
                "ground_truth": expected["answer"],
                "case_id": case["case_id"],
            }
        )
    return rows


def run_ragas_example() -> None:
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_recall, faithfulness
    except ImportError:
        print("Ragas example skipped. Install optional dependencies with: pip install ragas datasets")
        return

    rows = build_ragas_rows()
    if not rows:
        print("No RAG cases found.")
        return

    dataset = Dataset.from_list(rows)
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_recall],
    )
    print(result)


if __name__ == "__main__":
    rows = build_ragas_rows()
    print(f"Prepared {len(rows)} RAG rows from {CASES_PATH}")
    run_ragas_example()
