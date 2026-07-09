# Agent State: Model Evaluation MVP

Date: 2026-07-08

## Objective

Execute the v0.1 model evaluation MVP with isolated subagents by domain.

Current scope is intentionally narrower than the original three-week roadmap:

- STT: 10 synthetic or non-production cases
- TTS: 10 synthetic or non-production cases
- LLM: 20 synthetic or non-production cases
- No paid API calls required
- No production data
- Simulated outputs are allowed to verify the evaluation system
- `jiwer` is installed locally in `eval_mvp/.venv`; use that Python for STT scoring.

This v0.1 proves the evaluation pipeline, not real model quality.

## Agent Ownership

| Agent | Domain | Write Scope |
|---|---|---|
| Worker A | STT/TTS cases and local scoring scripts | `eval_mvp/cases/stt_cases.jsonl`, `eval_mvp/cases/tts_cases.jsonl`, `eval_mvp/scorers/*` |
| Worker B | LLM cases and tool configs | `eval_mvp/cases/llm_cases.jsonl`, `eval_mvp/configs/*` |
| Worker C | Reporting contract and dashboard data | `eval_mvp/reports/sample_*`, `eval_mvp/reports/build_dashboard_data.py`, `dashboard_data.js` |
| Worker D | Release package and operator docs | `eval_mvp/README.md`, `eval_mvp/reports/v0.*`, `eval_mvp/reports/user_action_required.md` |
| Main thread | Coordination, integration review, final verification | `eval_mvp/AGENT_STATE.md` and final integration only |

## Integration Rules

1. Do not overwrite files outside assigned ownership.
2. Preserve unrelated existing files.
3. All scripts must run without API keys in v0.1.
4. External tools may be described as optional, but local syntax checks must not require them.
5. If a real model, API key, real audio, real text, or production data is required, stop and record the required user action.
6. Dashboard data must remain compatible with existing `app.js`: `updatedAt`, `status`, `failureModes`, `phases`.

## Pause Conditions

Pause for user input only when one of these is required:

- Business scenario selection
- Evaluation language selection
- Candidate model list
- API key or paid service
- Real or脱敏 production data
- TTS fixed `voice_id`
- Human rating participants
- Permission to install dependencies

## Current Status

- Worker A: done
- Worker B: done
- Worker C: done_with_concerns; Python cache path required `PYTHONPYCACHEPREFIX=/private/tmp/model_eval_pycache` for py_compile
- Worker D: done
- Main thread: integrating and verifying worker outputs
