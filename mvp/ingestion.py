"""Parse and validate evaluation case and output files."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


CASE_FIELDS = {
    "STT": {
        "case_id": str,
        "scenario": str,
        "language": str,
        "reference_text": str,
        "critical_entities": list,
    },
    "TTS": {
        "case_id": str,
        "scenario": str,
        "language": str,
        "input_text": str,
        "critical_entities": list,
    },
    "LLM": {
        "case_id": str,
        "task_type": str,
        "input": str,
        "expected": dict,
        "assertions": list,
    },
}

OUTPUT_FIELDS = {
    "STT": {"case_id": str, "transcript": str},
    "TTS": {"case_id": str, "roundtrip_text": str},
    "LLM": {"case_id": str, "output": (str, dict)},
}

JSON_FIELDS = {
    "critical_entities",
    "risk_tags",
    "must_not_fail",
    "expected",
    "assertions",
    "context",
}

STT_ALIASES = ("prediction", "predicted_text", "output_text")


def _issue(
    code: str,
    path: Path,
    line: int,
    field: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "error_code": code,
        "filename": path.name,
        "line": line,
        "field": field,
        "reason": reason,
    }


ParseResult = Tuple[List[Tuple[int, Dict[str, Any]]], List[Dict[str, Any]], int]


def _parse_jsonl(path: Path) -> ParseResult:
    records: List[Tuple[int, Dict[str, Any]]] = []
    errors: List[Dict[str, Any]] = []
    attempted_records = 0
    try:
        with path.open("r", encoding="utf-8") as source:
            for line_number, raw_line in enumerate(source, 1):
                if not raw_line.strip():
                    continue
                attempted_records += 1
                try:
                    value = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    errors.append(
                        _issue("INVALID_JSON", path, line_number, "", str(exc))
                    )
                    continue
                if not isinstance(value, dict):
                    errors.append(
                        _issue(
                            "INVALID_RECORD",
                            path,
                            line_number,
                            "",
                            "JSONL record must be an object",
                        )
                    )
                    continue
                records.append((line_number, value))
    except UnicodeDecodeError:
        errors.append(_issue("INVALID_ENCODING", path, 1, "", "file must be UTF-8"))
    return records, errors, attempted_records


def _parse_csv(path: Path) -> ParseResult:
    records: List[Tuple[int, Dict[str, Any]]] = []
    errors: List[Dict[str, Any]] = []
    attempted_records = 0
    try:
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            if reader.fieldnames is None:
                return (
                    [],
                    [_issue("INVALID_CSV", path, 1, "", "CSV header is required")],
                    0,
                )
            headers = reader.fieldnames
            if any(not header.strip() for header in headers):
                return (
                    [],
                    [_issue("INVALID_CSV", path, 1, "", "CSV headers cannot be blank")],
                    0,
                )
            if len(set(headers)) != len(headers):
                return (
                    [],
                    [_issue("INVALID_CSV", path, 1, "", "CSV headers must be unique")],
                    0,
                )
            for line_number, row in enumerate(reader, 2):
                attempted_records += 1
                parsed: Dict[str, Any] = dict(row)
                for field in JSON_FIELDS.intersection(parsed):
                    value = parsed[field]
                    if value in (None, ""):
                        continue
                    try:
                        parsed[field] = json.loads(value)
                    except json.JSONDecodeError:
                        errors.append(
                            _issue(
                                "INVALID_JSON",
                                path,
                                line_number,
                                field,
                                "field must contain valid JSON",
                            )
                        )
                output = parsed.get("output")
                if output and output.lstrip().startswith("{"):
                    try:
                        parsed["output"] = json.loads(output)
                    except json.JSONDecodeError:
                        errors.append(
                            _issue(
                                "INVALID_JSON",
                                path,
                                line_number,
                                "output",
                                "object output must contain valid JSON",
                            )
                        )
                records.append((line_number, parsed))
    except UnicodeDecodeError:
        errors.append(_issue("INVALID_ENCODING", path, 1, "", "file must be UTF-8"))
    except csv.Error as exc:
        errors.append(
            _issue(
                "INVALID_CSV",
                path,
                max(attempted_records + 2, 1),
                "",
                str(exc),
            )
        )
    return records, errors, attempted_records


def _parse(path: Path) -> ParseResult:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return _parse_jsonl(path)
    if suffix == ".csv":
        return _parse_csv(path)
    return [], [_issue("INVALID_FILE_TYPE", path, 1, "", "use .jsonl or .csv")], 0


def _validate_required(
    path: Path,
    line: int,
    record: Dict[str, Any],
    fields: Dict[str, Any],
) -> List[Dict[str, Any]]:
    errors = []
    for field, expected_type in fields.items():
        if field not in record or record[field] is None or (
            field == "case_id"
            and isinstance(record[field], str)
            and not record[field].strip()
        ):
            errors.append(
                _issue("MISSING_FIELD", path, line, field, "required field is missing")
            )
        elif not isinstance(record[field], expected_type):
            errors.append(
                _issue(
                    "INVALID_FIELD_TYPE",
                    path,
                    line,
                    field,
                    "required field has the wrong type",
                )
            )
    return errors


def validate_files(model_type: str, cases_path: Path, outputs_path: Path) -> Dict[str, Any]:
    """Return canonical records and stable validation diagnostics."""
    cases_path = Path(cases_path)
    outputs_path = Path(outputs_path)
    if not isinstance(model_type, str) or model_type.upper() not in CASE_FIELDS:
        return {
            "status": "invalid",
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
            "errors": [
                _issue(
                    "INVALID_MODEL_TYPE",
                    cases_path,
                    0,
                    "model_type",
                    "model_type must be STT, TTS, or LLM",
                )
            ],
            "warnings": [],
            "cases": [],
            "outputs": [],
        }
    model_type = model_type.upper()

    case_rows, case_errors, total_case_records = _parse(cases_path)
    output_rows, output_errors, _ = _parse(outputs_path)
    errors = case_errors + output_errors
    warnings: List[Dict[str, Any]] = []
    cases: List[Dict[str, Any]] = []
    outputs: List[Dict[str, Any]] = []
    case_ids = set()
    case_parse_error_lines = {
        error["line"]
        for error in case_errors
        if error["line"] > 0
    }

    for line, record in case_rows:
        row_errors = _validate_required(
            cases_path, line, record, CASE_FIELDS[model_type]
        )
        case_id = record.get("case_id")
        if isinstance(case_id, str) and case_id:
            if case_id in case_ids:
                row_errors.append(
                    _issue(
                        "DUPLICATE_CASE_ID",
                        cases_path,
                        line,
                        "case_id",
                        "case_id must be unique",
                    )
                )
            else:
                case_ids.add(case_id)
        errors.extend(row_errors)
        if not row_errors and line not in case_parse_error_lines:
            cases.append(record)

    matched_output_ids = set()
    seen_output_ids = set()
    for line, original in output_rows:
        record = dict(original)
        if model_type == "STT" and "transcript" not in record:
            for alias in STT_ALIASES:
                if alias in record:
                    record["transcript"] = record[alias]
                    break

        row_errors = _validate_required(
            outputs_path, line, record, OUTPUT_FIELDS[model_type]
        )
        errors.extend(row_errors)
        if row_errors:
            continue

        case_id = record["case_id"]
        if case_id not in case_ids:
            warnings.append(
                _issue(
                    "UNKNOWN_OUTPUT_CASE_ID",
                    outputs_path,
                    line,
                    "case_id",
                    "output case_id does not exist in cases",
                )
            )
            continue
        if case_id in seen_output_ids:
            errors.append(
                _issue(
                    "DUPLICATE_OUTPUT_CASE_ID",
                    outputs_path,
                    line,
                    "case_id",
                    "output case_id must be unique",
                )
            )
            continue
        seen_output_ids.add(case_id)
        outputs.append(record)
        matched_output_ids.add(case_id)

    for line, record in case_rows:
        case_id = record.get("case_id")
        if case_id in case_ids and case_id not in matched_output_ids:
            warnings.append(
                _issue(
                    "MISSING_OUTPUT",
                    cases_path,
                    line,
                    "case_id",
                    f"no output found for {case_id}",
                )
            )

    valid_records = len(cases)
    return {
        "status": "invalid" if errors else "valid",
        "total_records": total_case_records,
        "valid_records": valid_records,
        "invalid_records": total_case_records - valid_records,
        "errors": errors,
        "warnings": warnings,
        "cases": cases,
        "outputs": outputs,
    }
