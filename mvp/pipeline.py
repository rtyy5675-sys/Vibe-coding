"""Task creation and fixture-mode scoring pipeline."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scorers.score_entities import index_by_case_id
from scorers.score_llm_rules import score_llm_case
from scorers.score_stt_jiwer import score_stt_cases
from scorers.score_tts_roundtrip import score_tts_roundtrip

from .reporting import generate_report
from .storage import Storage


SCORER_VERSION = "mvp-fixture-v0.1"
TERMINAL_ITEM_STATUSES = {"succeeded", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                records.append(json.loads(line))
    return records


def _task_summary(storage: Storage, task_id: str) -> dict[str, Any] | None:
    with storage.connect() as connection:
        connection.row_factory = lambda cursor, row: {
            column[0]: row[index] for index, column in enumerate(cursor.description)
        }
        task = connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if task is None:
            return None
        rows = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(status = 'pending') AS pending,
                SUM(status = 'running') AS running,
                SUM(status = 'succeeded') AS succeeded,
                SUM(status = 'failed') AS failed
            FROM task_items WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        review_required = connection.execute(
            """
            SELECT COUNT(*) AS review_required
            FROM (
                SELECT case_id
                FROM results
                WHERE task_id = ? AND human_review_required = 1
                UNION
                SELECT case_id
                FROM task_items
                WHERE task_id = ? AND status = 'failed'
            )
            """,
            (task_id, task_id),
        ).fetchone()["review_required"]
        report = connection.execute(
            "SELECT status, html_path, csv_path FROM reports WHERE task_id = ?",
            (task_id,),
        ).fetchone()

    counts = {key: int(rows[key] or 0) for key in ("total", "pending", "running", "succeeded", "failed")}
    counts["review_required"] = int(review_required or 0)
    finished = counts["succeeded"] + counts["failed"]
    progress = int((finished / counts["total"]) * 100) if counts["total"] else 0
    report_ready = bool(
        report
        and report["status"] == "ready"
        and report["html_path"]
        and report["csv_path"]
        and Path(report["html_path"]).is_file()
        and Path(report["csv_path"]).is_file()
    )
    return {
        "task_id": task_id,
        "model_type": task["model_type"],
        "dataset_version": task["dataset_version"],
        "status": task["status"],
        "progress": progress,
        "counts": counts,
        "report_status": "ready" if report_ready else "pending",
        "report_path": report["html_path"] if report_ready else None,
        "csv_path": report["csv_path"] if report_ready else None,
    }


def get_task(storage: Storage, task_id: str) -> dict[str, Any] | None:
    return _task_summary(storage, task_id)


def list_recent_tasks(storage: Storage, limit: int = 20) -> list[dict[str, Any]]:
    with storage.connect() as connection:
        connection.row_factory = lambda cursor, row: {
            column[0]: row[index] for index, column in enumerate(cursor.description)
        }
        rows = connection.execute(
            """
            SELECT
                t.task_id, t.model_type, t.status, t.created_at,
                COALESCE(r.status, 'pending') AS report_status
            FROM tasks t
            LEFT JOIN reports r ON r.task_id = t.task_id
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return list(rows)


def create_task(storage: Storage, runtime_root: Path, upload_id: str, runner_mode: str) -> dict[str, Any]:
    if runner_mode != "fixture":
        raise ValueError("runner_mode must be fixture")
    with storage.connect() as connection:
        connection.row_factory = lambda cursor, row: {
            column[0]: row[index] for index, column in enumerate(cursor.description)
        }
        dataset = connection.execute(
            """
            SELECT d.*, u.model_type
            FROM datasets d JOIN uploads u ON u.upload_id = d.upload_id
            WHERE d.upload_id = ?
            """,
            (upload_id,),
        ).fetchone()
        if dataset is None:
            raise LookupError("upload_id not found")
        cases = _load_jsonl(dataset["canonical_cases_path"])
        task_id = "task_" + uuid.uuid4().hex[:16]
        timestamp = _now()
        connection.execute(
            """
            INSERT INTO tasks (
                task_id, dataset_version, model_type, runner_mode, status,
                scorer_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                dataset["dataset_version"],
                dataset["model_type"],
                runner_mode,
                "queued",
                SCORER_VERSION,
                timestamp,
            ),
        )
        connection.executemany(
            """
            INSERT INTO task_items (
                task_id, case_id, status, attempt_count, error_message
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [(task_id, str(case["case_id"]), "pending", 0, None) for case in cases],
        )

    summary = _task_summary(storage, task_id)
    return summary if summary is not None else {"task_id": task_id, "status": "queued"}


def _store_result(
    connection,
    task_id: str,
    case_id: str,
    dataset_version: str,
    metric: str,
    score: float | None,
    severity: str,
    business_usability: str,
    human_review_required: bool,
    run_status: str,
    notes: str = "",
) -> None:
    connection.execute(
        """
        INSERT INTO results (
            result_id, task_id, case_id, metric, score, severity, business_usability,
            human_review_required, scorer, scorer_version, dataset_version,
            run_status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            task_id,
            case_id,
            metric,
            score,
            severity,
            business_usability,
            1 if human_review_required else 0,
            SCORER_VERSION,
            SCORER_VERSION,
            dataset_version,
            run_status,
            notes,
        ),
    )


def _claim_item(
    connection,
    task_id: str,
    case_id: str,
    allowed_statuses: tuple[str, ...],
) -> bool:
    placeholders = ",".join("?" for _ in allowed_statuses)
    cursor = connection.execute(
        """
        UPDATE task_items
        SET status = 'running', attempt_count = attempt_count + 1,
            error_message = NULL, started_at = ?
        WHERE task_id = ? AND case_id = ? AND status IN (%s)
        """ % placeholders,
        (_now(), task_id, case_id, *allowed_statuses),
    )
    return cursor.rowcount == 1


def _start_task_run(connection, task_id: str, retry: bool) -> bool:
    allowed_statuses = (
        ("queued", "partially_completed", "failed")
        if retry
        else ("queued",)
    )
    placeholders = ",".join("?" for _ in allowed_statuses)
    cursor = connection.execute(
        """
        UPDATE tasks
        SET status = ?, started_at = COALESCE(started_at, ?)
        WHERE task_id = ? AND status IN (%s)
        """ % placeholders,
        ("running", _now(), task_id, *allowed_statuses),
    )
    return cursor.rowcount == 1


def claim_retry_task(storage: Storage, task_id: str) -> str | None:
    with storage.connect() as connection:
        row = connection.execute(
            "SELECT status FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None or row[0] not in {"partially_completed", "failed"}:
            return None
        next_status = "queued" if row[0] == "failed" else "running"
        cursor = connection.execute(
            """
            UPDATE tasks
            SET status = ?, started_at = COALESCE(started_at, ?)
            WHERE task_id = ? AND status IN (?, ?)
            """,
            (next_status, _now(), task_id, "partially_completed", "failed"),
        )
    return next_status if cursor.rowcount == 1 else None


def _score_case(model_type: str, case: dict[str, Any], output: dict[str, Any] | None) -> list[dict[str, Any]]:
    if output is None:
        raise ValueError("missing fixture output")
    if model_type == "STT":
        score = score_stt_cases([case], [output])[0]
        failed_entity = not bool(score["entity_pass"])
        return [
            {"metric": "wer", "score": score["wer"], "passed": score["wer"] == 0, "review": False, "notes": ""},
            {"metric": "cer", "score": score["cer"], "passed": score["cer"] == 0, "review": False, "notes": ""},
            {
                "metric": "entity_pass",
                "score": 1.0 if score["entity_pass"] else 0.0,
                "passed": bool(score["entity_pass"]),
                "review": failed_entity,
                "notes": json.dumps(score["missing_entities"], ensure_ascii=False),
            },
            {
                "metric": "entity_score",
                "score": score["entity_score"],
                "passed": bool(score["entity_pass"]),
                "review": failed_entity,
                "notes": json.dumps(score["missing_entities"], ensure_ascii=False),
            },
        ]
    if model_type == "TTS":
        score = score_tts_roundtrip([case], [output])[0]
        review = bool(case.get("human_review_required")) or not bool(score["entity_pass"])
        return [
            {
                "metric": "entity_pass",
                "score": 1.0 if score["entity_pass"] else 0.0,
                "passed": bool(score["entity_pass"]),
                "review": review,
                "notes": json.dumps(score["missing_entities"], ensure_ascii=False),
            },
            {
                "metric": "entity_score",
                "score": score["entity_score"],
                "passed": bool(score["entity_pass"]),
                "review": review,
                "notes": json.dumps(score["missing_entities"], ensure_ascii=False),
            },
        ]
    if model_type == "LLM":
        return [
            {**item, "review": not item["passed"]}
            for item in score_llm_case(case, output)
        ]
    raise ValueError("unsupported model_type")


def run_task(
    storage: Storage,
    runtime_root: Path,
    task_id: str,
    retry: bool,
    already_started: bool = False,
) -> None:
    with storage.connect() as connection:
        connection.row_factory = lambda cursor, row: {
            column[0]: row[index] for index, column in enumerate(cursor.description)
        }
        task = connection.execute(
            """
            SELECT t.*, d.canonical_cases_path, d.canonical_outputs_path
            FROM tasks t JOIN datasets d ON d.dataset_version = t.dataset_version
            WHERE t.task_id = ?
            """,
            (task_id,),
        ).fetchone()
        if task is None:
            raise LookupError("task not found")
        if task["status"] in {"completed"} and not retry:
            return
        if not already_started and not _start_task_run(connection, task_id, retry):
            return
        item_statuses = ("pending", "failed") if retry else ("pending",)
        items = connection.execute(
            "SELECT * FROM task_items WHERE task_id = ? AND status IN (%s) ORDER BY case_id" % (
                ",".join("?" for _ in item_statuses)
            ),
            (task_id, *item_statuses),
        ).fetchall()

    cases = _load_jsonl(task["canonical_cases_path"])
    outputs = _load_jsonl(task["canonical_outputs_path"])
    case_index = {str(case["case_id"]): case for case in cases}
    output_index = index_by_case_id(outputs)

    for item in items:
        case_id = item["case_id"]
        with storage.connect() as connection:
            claimed = _claim_item(connection, task_id, case_id, item_statuses)
        if not claimed:
            continue
        try:
            score_rows = _score_case(task["model_type"], case_index[case_id], output_index.get(case_id))
            with storage.connect() as connection:
                connection.execute(
                    "DELETE FROM results WHERE task_id = ? AND case_id = ?",
                    (task_id, case_id),
                )
                for score in score_rows:
                    passed = bool(score.get("passed"))
                    _store_result(
                        connection,
                        task_id,
                        case_id,
                        task["dataset_version"],
                        str(score["metric"]),
                        score.get("score"),
                        "info" if passed else "major",
                        "usable" if passed else "review_required",
                        bool(score.get("review")),
                        "succeeded",
                        str(score.get("notes", "")),
                    )
                connection.execute(
                    """
                    UPDATE task_items
                    SET status = 'succeeded', completed_at = ?
                    WHERE task_id = ? AND case_id = ?
                    """,
                    (_now(), task_id, case_id),
                )
        except Exception as exc:
            with storage.connect() as connection:
                connection.execute(
                    """
                    UPDATE task_items
                    SET status = 'failed', error_message = ?, completed_at = ?
                    WHERE task_id = ? AND case_id = ?
                    """,
                    (str(exc), _now(), task_id, case_id),
                )

    with storage.connect() as connection:
        counts = connection.execute(
            """
            SELECT
                SUM(status = 'succeeded') AS succeeded,
                SUM(status = 'failed') AS failed,
                COUNT(*) AS total
            FROM task_items WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
        status = "completed"
        if counts[1]:
            status = "partially_completed" if counts[0] else "failed"
        connection.execute(
            "UPDATE tasks SET status = ?, completed_at = ? WHERE task_id = ?",
            (status, _now(), task_id),
        )
    generate_report(storage, runtime_root, task_id)


def recover_interrupted_tasks(storage: Storage) -> None:
    with storage.connect() as connection:
        task_ids = [
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT task_id FROM task_items WHERE status = 'running'"
            )
        ]
        if not task_ids:
            return
        connection.execute(
            """
            UPDATE task_items
            SET status = 'failed',
                error_message = COALESCE(error_message, 'interrupted before completion'),
                completed_at = COALESCE(completed_at, ?)
            WHERE status = 'running'
            """,
            (_now(),),
        )
        for task_id in task_ids:
            succeeded, failed = connection.execute(
                """
                SELECT SUM(status = 'succeeded'), SUM(status = 'failed')
                FROM task_items WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            status = "partially_completed" if succeeded and failed else "failed"
            connection.execute(
                "UPDATE tasks SET status = ?, completed_at = ? WHERE task_id = ?",
                (status, _now(), task_id),
            )


def retry_report(storage: Storage, runtime_root: Path, task_id: str) -> dict[str, Any]:
    summary = _task_summary(storage, task_id)
    if summary is None:
        raise LookupError("task not found")
    if summary["status"] not in {"completed", "partially_completed", "failed"}:
        raise ValueError("report cannot be retried from " + summary["status"])
    generate_report(storage, runtime_root, task_id)
    return _task_summary(storage, task_id) or summary


def retry_task(storage: Storage, runtime_root: Path, task_id: str) -> dict[str, Any]:
    claimed_status = claim_retry_task(storage, task_id)
    if claimed_status is None:
        raise ValueError("task cannot be retried")
    run_task(
        storage,
        runtime_root,
        task_id,
        retry=True,
        already_started=claimed_status == "running",
    )
    summary = _task_summary(storage, task_id)
    if summary is None:
        raise LookupError("task not found")
    return summary
