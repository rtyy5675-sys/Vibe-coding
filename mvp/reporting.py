"""Generate HTML and CSV reports for completed fixture tasks."""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import Storage


CSV_FIELDS = [
    "task_id",
    "case_id",
    "model_type",
    "metric",
    "score",
    "severity",
    "business_usability",
    "human_review_required",
    "scorer",
    "scorer_version",
    "dataset_version",
    "run_status",
    "notes",
]


def _fetch_rows(storage: Storage, task_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    with storage.connect() as connection:
        connection.row_factory = lambda cursor, row: {
            column[0]: row[index] for index, column in enumerate(cursor.description)
        }
        task = connection.execute(
            """
            SELECT t.*, d.canonical_cases_path
            FROM tasks t
            JOIN datasets d ON d.dataset_version = t.dataset_version
            WHERE t.task_id = ?
            """,
            (task_id,),
        ).fetchone()
        items = connection.execute(
            "SELECT * FROM task_items WHERE task_id = ? ORDER BY case_id",
            (task_id,),
        ).fetchall()
        results = connection.execute(
            """
            SELECT r.*, t.model_type
            FROM results r
            JOIN tasks t ON t.task_id = r.task_id
            WHERE r.task_id = ?
            ORDER BY r.case_id, r.metric
            """,
            (task_id,),
        ).fetchall()
    if task is None:
        raise ValueError("task not found")
    return task, items, results


def _load_cases_by_id(path: str) -> dict[str, dict[str, Any]]:
    cases = {}
    with Path(path).open("r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                record = json.loads(line)
                cases[str(record["case_id"])] = record
    return cases


def _count_by(values: list[str]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return "\n".join(
        "<li>%s: %s</li>" % (html.escape(key), count)
        for key, count in sorted(counts.items())
    )


def generate_report(storage: Storage, runtime_root: Path, task_id: str) -> dict[str, str]:
    task, items, results = _fetch_rows(storage, task_id)
    cases_by_id = _load_cases_by_id(task["canonical_cases_path"])
    report_dir = runtime_root / "reports" / "generated" / task_id
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "results.csv"
    html_path = report_dir / "report.html"

    result_by_case = {row["case_id"]: row for row in results}
    csv_rows: list[dict[str, Any]] = []
    for result in results:
        csv_rows.append({field: result.get(field, "") for field in CSV_FIELDS})
    for item in items:
        if item["case_id"] not in result_by_case:
            csv_rows.append({
                "task_id": task_id,
                "case_id": item["case_id"],
                "model_type": task["model_type"],
                "metric": "run_status",
                "score": "",
                "severity": "major",
                "business_usability": "blocked",
                "human_review_required": 1,
                "scorer": task["scorer_version"],
                "scorer_version": task["scorer_version"],
                "dataset_version": task["dataset_version"],
                "run_status": item["status"],
                "notes": item["error_message"] or "",
            })

    with csv_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_rows)

    total = len(items)
    succeeded = sum(1 for item in items if item["status"] == "succeeded")
    failed = sum(1 for item in items if item["status"] == "failed")
    review_required = sum(1 for row in csv_rows if int(row.get("human_review_required") or 0))
    generated_at = datetime.now(timezone.utc).isoformat()
    covered_cases = {row["case_id"] for row in results}
    coverage = round((len(covered_cases) / total) * 100, 2) if total else 0
    major_rows = [row for row in csv_rows if row.get("severity") in {"critical", "major"}]
    metrics = sorted({str(row.get("metric", "")) for row in csv_rows if row.get("metric")})
    scenario_items = _count_by([
        str(cases_by_id.get(str(item["case_id"]), {}).get("scenario", "unknown"))
        for item in items
    ])
    severity_items = _count_by([
        str(row.get("severity") or "unknown")
        for row in csv_rows
    ])

    detail_items = "\n".join(
        "<li>%s · %s · %s</li>" % (
            html.escape(str(row["case_id"])),
            html.escape(str(row["metric"])),
            html.escape(str(row.get("notes", ""))),
        )
        for row in major_rows
    )
    html_path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Evaluation Report {html.escape(task_id)}</title></head>
<body>
<h1>模型自动化评估报告</h1>
<p>task_id: {html.escape(task_id)}</p>
<p>generated_at: {html.escape(generated_at)}</p>
<p>model_type: {html.escape(task['model_type'])}</p>
<p>dataset_version: {html.escape(task['dataset_version'])}</p>
<p>scorer: {html.escape(task['scorer_version'])}</p>
<p>scorer_version: {html.escape(task['scorer_version'])}</p>
<p>fixture 模式结果仅用于验证评估链路，不代表真实模型质量结论。</p>
<table border="1">
<tr><th>total</th><th>succeeded</th><th>failed</th><th>review_required</th><th>coverage</th></tr>
<tr><td>{total}</td><td>{succeeded}</td><td>{failed}</td><td>{review_required}</td><td>{coverage}%</td></tr>
</table>
<h2>Critical / Major 明细</h2>
<ul>{detail_items}</ul>
<h2>Scenario 汇总</h2>
<ul>{scenario_items}</ul>
<h2>Severity 汇总</h2>
<ul>{severity_items}</ul>
<h2>指标汇总</h2>
<p>{html.escape(', '.join(metrics))}</p>
</body>
</html>
""",
        encoding="utf-8",
    )

    with storage.connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO reports (
                report_id, task_id, status, html_path, csv_path, template_version, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "report-" + task_id,
                task_id,
                "ready",
                str(html_path),
                str(csv_path),
                "mvp-v0.1",
                generated_at,
            ),
        )
    return {"html_path": str(html_path), "csv_path": str(csv_path)}
