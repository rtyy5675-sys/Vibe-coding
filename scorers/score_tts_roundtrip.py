#!/usr/bin/env python3
"""Score TTS round-trip STT text with the shared entity checker."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .score_entities import check_entities, index_by_case_id, load_jsonl, output_text
except ImportError:  # pragma: no cover - keeps direct CLI execution working
    from score_entities import check_entities, index_by_case_id, load_jsonl, output_text


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "reports" / "tts_roundtrip_scores.jsonl"


def score_tts_roundtrip(
    cases: list[dict[str, Any]], outputs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    output_index = index_by_case_id(outputs)
    scores: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id", ""))
        output = output_index.get(case_id, {})
        roundtrip_text = output_text(output)
        entity_score = check_entities(case, roundtrip_text)
        scores.append(
            {
                "case_id": case_id,
                "scenario": case.get("scenario"),
                "has_output": bool(output),
                "entity_pass": entity_score["entity_pass"],
                "entity_score": entity_score["entity_score"],
                "missing_entities": entity_score["missing_entities"],
                "input_text": case.get("input_text", ""),
                "roundtrip_text": roundtrip_text,
                "human_review_required": bool(case.get("human_review_required", False)),
            }
        )
    return scores


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score TTS round-trip output JSONL with critical entity checks."
    )
    parser.add_argument("tts_cases_jsonl", help="TTS case JSONL.")
    parser.add_argument("tts_roundtrip_outputs_jsonl", help="Round-trip STT output JSONL keyed by case_id.")
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Destination score JSONL. Defaults to {DEFAULT_OUTPUT}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scores = score_tts_roundtrip(
        load_jsonl(args.tts_cases_jsonl),
        load_jsonl(args.tts_roundtrip_outputs_jsonl),
    )
    write_jsonl(scores, Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
