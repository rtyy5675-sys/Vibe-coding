#!/usr/bin/env python3
"""Score STT transcripts with jiwer when available, plus local entity checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from score_entities import check_entities, index_by_case_id, load_jsonl, output_text


try:
    import jiwer  # type: ignore
except ImportError:  # pragma: no cover - depends on local environment
    jiwer = None


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "reports" / "stt_scores.jsonl"


def normalize_metric_text(text: str) -> str:
    return " ".join(text.casefold().split())


def edit_distance(left: list[str] | str, right: list[str] | str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_item in enumerate(left, start=1):
        current = [i]
        for j, right_item in enumerate(right, start=1):
            cost = 0 if left_item == right_item else 1
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + cost,
                )
            )
        previous = current
    return previous[-1]


def fallback_wer(reference: str, hypothesis: str) -> float:
    reference_words = normalize_metric_text(reference).split()
    hypothesis_words = normalize_metric_text(hypothesis).split()
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    return edit_distance(reference_words, hypothesis_words) / len(reference_words)


def fallback_cer(reference: str, hypothesis: str) -> float:
    reference_chars = list(normalize_metric_text(reference))
    hypothesis_chars = list(normalize_metric_text(hypothesis))
    if not reference_chars:
        return 0.0 if not hypothesis_chars else 1.0
    return edit_distance(reference_chars, hypothesis_chars) / len(reference_chars)


def metric_scores(reference: str, hypothesis: str) -> tuple[float, float, str]:
    if jiwer is not None:
        return float(jiwer.wer(reference, hypothesis)), float(jiwer.cer(reference, hypothesis)), "jiwer"
    return fallback_wer(reference, hypothesis), fallback_cer(reference, hypothesis), "fallback"


def score_stt_cases(cases: list[dict[str, Any]], outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output_index = index_by_case_id(outputs)
    scores: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id", ""))
        reference = str(case.get("reference_text", ""))
        output = output_index.get(case_id, {})
        hypothesis = output_text(output)
        wer_value, cer_value, metric_source = metric_scores(reference, hypothesis)
        entity_score = check_entities(case, hypothesis)
        scores.append(
            {
                "case_id": case_id,
                "scenario": case.get("scenario"),
                "has_output": bool(output),
                "metric_source": metric_source,
                "wer": wer_value,
                "cer": cer_value,
                "entity_pass": entity_score["entity_pass"],
                "entity_score": entity_score["entity_score"],
                "missing_entities": entity_score["missing_entities"],
                "reference_text": reference,
                "hypothesis_text": hypothesis,
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
        description="Score STT output JSONL with WER/CER and critical entity checks."
    )
    parser.add_argument("stt_cases_jsonl", help="STT case JSONL.")
    parser.add_argument("stt_outputs_jsonl", help="STT output JSONL keyed by case_id.")
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Destination score JSONL. Defaults to {DEFAULT_OUTPUT}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scores = score_stt_cases(load_jsonl(args.stt_cases_jsonl), load_jsonl(args.stt_outputs_jsonl))
    write_jsonl(scores, Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
