"""Minimal DeepEval pytest example for v0.1 LLM cases.

This file is intentionally safe to import without paid API keys. If DeepEval is
not installed, the pytest tests are skipped with a clear message.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    import pytest
except ImportError:  # pragma: no cover
    pytest = None

try:
    from deepeval import assert_test
    from deepeval.metrics import AnswerRelevancyMetric
    from deepeval.test_case import LLMTestCase
except ImportError:  # pragma: no cover
    assert_test = None
    AnswerRelevancyMetric = None
    LLMTestCase = None


CASES_PATH = Path(__file__).resolve().parents[1] / "cases" / "llm_cases.jsonl"


def load_cases(task_type: str | None = None) -> list[dict]:
    cases: list[dict] = []
    with CASES_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            case = json.loads(line)
            if task_type is None or case.get("task_type") == task_type:
                cases.append(case)
    return cases


def mock_model_output(case: dict) -> str:
    """Offline placeholder: returns expected output as if a model answered."""
    expected = case.get("expected", {})
    return json.dumps(expected, ensure_ascii=False, sort_keys=True)


def require_deepeval() -> None:
    if pytest is None:
        raise RuntimeError("pytest is required to run this example: pip install pytest")
    if assert_test is None or AnswerRelevancyMetric is None or LLMTestCase is None:
        pytest.skip("DeepEval is not installed. Install with: pip install deepeval")


def test_llm_cases_jsonl_is_readable() -> None:
    cases = load_cases()
    assert len(cases) == 20
    assert all({"case_id", "task_type", "input", "expected", "assertions", "risk_tags"} <= set(case) for case in cases)


def test_structured_cases_have_expected_entities() -> None:
    for case in load_cases("structured_extraction"):
        output = mock_model_output(case)
        for value in case["expected"].values():
            assert str(value) in output


def test_deepeval_answer_relevancy_smoke() -> None:
    require_deepeval()
    case = load_cases("business_flow")[0]
    test_case = LLMTestCase(
        input=case["input"],
        actual_output=mock_model_output(case),
        expected_output=json.dumps(case["expected"], ensure_ascii=False),
    )
    metric = AnswerRelevancyMetric(threshold=0.5)
    assert_test(test_case, [metric])


if __name__ == "__main__":
    loaded = load_cases()
    print(f"Loaded {len(loaded)} LLM cases from {CASES_PATH}")
    print("Run with pytest for checks. DeepEval-specific tests skip if deepeval is not installed.")
