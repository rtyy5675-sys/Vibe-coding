# v0.1 Reporting Contract

This contract defines the normalized report shape consumed by the local model evaluation dashboard. Tool-specific outputs should be preserved in `eval_mvp/runs/`; only normalized rows should enter `eval_mvp/reports/`.

## Canonical Fields

Every row in `sample_eval_summary.csv` and `sample_tool_results.jsonl` must include:

| Field | Required | Description |
|---|---:|---|
| `model_type` | Yes | Evaluation target family: `STT`, `TTS`, or `LLM`. |
| `case_id` | Yes | Stable case identifier from `eval_mvp/cases/`. |
| `tool` | Yes | Human-readable tool or scorer name, such as `Promptfoo`, `DeepEval`, `Ragas`, `JiWER`, `HumanMOS`, or `EntityRules`. |
| `source` | Yes | Normalized source identifier. Allowed v0.1 values: `promptfoo`, `deepeval`, `ragas`, `jiwer`, `human`. |
| `metric` | Yes | Metric name after normalization, for example `wer`, `faithfulness`, `json_schema_pass_rate`, or `naturalness_mos`. |
| `score` | Yes | Numeric score. Preserve source scale, then document it in `notes` when the scale is not 0-1. |
| `severity` | Yes | Business risk label: `Critical`, `Major`, or `Minor`. |
| `business_usability` | Yes | Operational decision label: `usable`, `review_required`, or `blocked`. |
| `human_review_required` | Yes | Boolean flag. Use `true` for all Critical rows and for any metric that cannot be trusted without human review. |
| `notes` | Yes | Short evidence note describing the observed behavior or conversion caveat. |

## Source Mapping

Promptfoo output enters the contract with `source=promptfoo`. Each assertion result should become one row using the prompt/model/case context as `case_id`, the assertion name as `metric`, and the pass rate or score as `score`.

DeepEval output enters with `source=deepeval`. Each pytest-style metric result should become one row. Use the DeepEval metric class or test name as `metric`, and keep trace-level evidence in `notes`.

Ragas output enters with `source=ragas`. Each RAG metric, such as faithfulness, context recall, or answer relevancy, should become one row per `case_id`.

JiWER output enters with `source=jiwer`. WER/CER rows should use JiWER scores directly. STT/TTS entity and round-trip checks that depend on JiWER transcripts may also use `source=jiwer` while naming the custom scorer in `tool`.

Human review output enters with `source=human`. MOS, scenario fit, naturalness, intelligibility, and manual risk review rows should preserve the reviewer-facing scale in `score` and explain that scale in `notes` when needed.

## Dashboard Integration

`build_dashboard_data.py` reads `sample_eval_summary.csv` and writes `outputs/model_eval_framework/dashboard_data.js` as `window.EVAL_DASHBOARD_DATA`.

The generated JavaScript must retain the existing front-end fields:

- `updatedAt`
- `status`
- `failureModes`
- `phases`

The dashboard is a summary view only. Raw tool output should stay in `runs/`; normalized rows should stay in `reports/`.
