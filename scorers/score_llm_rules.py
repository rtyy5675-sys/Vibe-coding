"""Deterministic LLM rule assertions for fixture-mode evaluation."""

from __future__ import annotations

import json
from typing import Any


SUPPORTED_ASSERTIONS = {
    "valid_json",
    "contains_required_fields",
    "exact_match_entities",
    "contains_required_facts",
    "does_not_contain_forbidden_steps",
    "no_hallucinated_entities",
    "does_not_contain_false_guarantee",
    "contains_limitation",
}


def _as_object(value: Any) -> tuple[dict[str, Any] | None, str]:
    if isinstance(value, dict):
        return value, json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = "" if value is None else str(value)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None, text
    return parsed if isinstance(parsed, dict) else None, text


def _contains_all(text: str, values: list[Any]) -> bool:
    lowered = text.casefold()
    return all(str(value).casefold() in lowered for value in values if value not in (None, ""))


def score_llm_case(case: dict[str, Any], output: dict[str, Any] | None) -> list[dict[str, Any]]:
    expected = case.get("expected", {})
    assertions = case.get("assertions", [])
    if not isinstance(expected, dict):
        expected = {}
    if not isinstance(assertions, list):
        assertions = []

    output_value = None if output is None else output.get("output")
    output_object, output_text = _as_object(output_value)
    scores: list[dict[str, Any]] = []

    for assertion in assertions:
        name = str(assertion)
        supported = name in SUPPORTED_ASSERTIONS
        passed = False
        notes = ""

        if not supported:
            notes = "unsupported assertion"
        elif name == "valid_json":
            passed = output_object is not None
        elif name == "contains_required_fields":
            passed = output_object is not None and all(key in output_object for key in expected)
        elif name == "exact_match_entities":
            passed = output_object is not None and all(output_object.get(key) == value for key, value in expected.items())
        elif name == "contains_required_facts":
            facts = list(expected.values()) if expected else []
            passed = _contains_all(output_text, facts)
        elif name == "does_not_contain_forbidden_steps":
            forbidden = expected.get("forbidden_steps", [])
            forbidden_values = forbidden if isinstance(forbidden, list) else [forbidden]
            forbidden_values = [
                value for value in forbidden_values if value not in (None, "")
            ]
            passed = not forbidden_values or not _contains_all(output_text, forbidden_values)
        elif name == "no_hallucinated_entities":
            allowed = {str(value).casefold() for value in expected.values()}
            values = output_object.values() if output_object else []
            passed = all(str(value).casefold() in allowed for value in values)
        elif name == "does_not_contain_false_guarantee":
            passed = "guarantee" not in output_text.casefold() and "保证" not in output_text
        elif name == "contains_limitation":
            passed = any(token in output_text.casefold() for token in ("cannot", "unable", "limitation", "无法", "不能"))

        scores.append({
            "metric": name,
            "score": 1.0 if passed else 0.0,
            "passed": passed,
            "supported": supported,
            "notes": notes,
        })

    if not scores:
        scores.append({
            "metric": "no_assertions",
            "score": 1.0,
            "passed": True,
            "supported": True,
            "notes": "no assertions configured",
        })
    return scores
