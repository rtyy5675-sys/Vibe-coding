#!/usr/bin/env python3
"""String-containment entity checks for local eval MVP JSONL files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


TEXT_FIELDS = (
    "output_text",
    "transcript",
    "prediction",
    "predicted_text",
    "text",
    "roundtrip_text",
)


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_no}: expected JSON object")
            records.append(record)
    return records


def write_jsonl(records: Iterable[dict[str, Any]], path: str | Path | None) -> None:
    if path is None or str(path) == "-":
        for record in records:
            print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_text(value: Any) -> str:
    return " ".join(str(value).casefold().split())


def output_text(record: dict[str, Any]) -> str:
    for field in TEXT_FIELDS:
        value = record.get(field)
        if value not in (None, ""):
            return str(value)
    return ""


def index_by_case_id(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        case_id = record.get("case_id")
        if case_id is None:
            continue
        indexed[str(case_id)] = record
    return indexed


def entity_value(entity: Any) -> str:
    if isinstance(entity, dict):
        return str(entity.get("value", ""))
    return str(entity)


def check_entities(
    case: dict[str, Any],
    candidate_text: str,
    entity_field: str = "critical_entities",
) -> dict[str, Any]:
    entities = case.get(entity_field, [])
    if entities is None:
        entities = []
    if not isinstance(entities, list):
        raise ValueError(f"{case.get('case_id', '<unknown>')}: {entity_field} must be a list")

    normalized_candidate = normalize_text(candidate_text)
    results: list[dict[str, Any]] = []
    for entity in entities:
        value = entity_value(entity)
        passed = bool(value) and normalize_text(value) in normalized_candidate
        item: dict[str, Any] = {
            "value": value,
            "passed": passed,
        }
        if isinstance(entity, dict) and "type" in entity:
            item["type"] = entity["type"]
        results.append(item)

    missing = [item for item in results if not item["passed"]]
    total = len(results)
    matched = total - len(missing)
    return {
        "case_id": case.get("case_id"),
        "entity_field": entity_field,
        "entity_pass": not missing,
        "entity_score": matched / total if total else 1.0,
        "matched_entity_count": matched,
        "critical_entity_count": total,
        "missing_entities": missing,
        "entity_results": results,
    }


def score_case_outputs(
    cases: Iterable[dict[str, Any]],
    outputs: Iterable[dict[str, Any]],
    entity_field: str = "critical_entities",
) -> list[dict[str, Any]]:
    output_index = index_by_case_id(outputs)
    scores: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id", ""))
        output = output_index.get(case_id, {})
        text = output_text(output)
        score = check_entities(case, text, entity_field=entity_field)
        score.update(
            {
                "case_id": case_id,
                "has_output": bool(output),
                "candidate_text": text,
            }
        )
        scores.append(score)
    return scores


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check critical_entities from case JSONL against model output JSONL."
    )
    parser.add_argument("cases_jsonl", help="Case JSONL with case_id and critical_entities.")
    parser.add_argument("outputs_jsonl", help="Output JSONL keyed by case_id.")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination JSONL path. Defaults to stdout.",
    )
    parser.add_argument(
        "--entity-field",
        default="critical_entities",
        help="Case field containing entity objects or strings.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scores = score_case_outputs(
        load_jsonl(args.cases_jsonl),
        load_jsonl(args.outputs_jsonl),
        entity_field=args.entity_field,
    )
    write_jsonl(scores, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
