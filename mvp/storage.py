"""SQLite schema and connection management for the evaluation MVP."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
BEGIN;
CREATE TABLE IF NOT EXISTS uploads (
    upload_id TEXT PRIMARY KEY,
    model_type TEXT NOT NULL,
    cases_path TEXT NOT NULL,
    outputs_path TEXT NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL,
    validation_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_version TEXT PRIMARY KEY,
    upload_id TEXT NOT NULL,
    canonical_cases_path TEXT NOT NULL,
    canonical_outputs_path TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (upload_id) REFERENCES uploads(upload_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    dataset_version TEXT NOT NULL,
    model_type TEXT NOT NULL,
    runner_mode TEXT NOT NULL,
    status TEXT NOT NULL,
    scorer_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY (dataset_version) REFERENCES datasets(dataset_version)
);

CREATE TABLE IF NOT EXISTS task_items (
    task_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL,
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    PRIMARY KEY (task_id, case_id),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    score REAL,
    severity TEXT,
    business_usability TEXT,
    human_review_required INTEGER NOT NULL,
    scorer TEXT NOT NULL,
    scorer_version TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    run_status TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (task_id, case_id) REFERENCES task_items(task_id, case_id)
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    status TEXT NOT NULL,
    html_path TEXT,
    csv_path TEXT,
    template_version TEXT NOT NULL,
    generated_at TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);
COMMIT;
"""


class Storage:
    """Own SQLite setup without coupling to ingestion or pipeline state."""

    def __init__(self, database_path: Path):
        self.database_path = Path(database_path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(results)")
            }
            if "dataset_version" not in columns:
                connection.execute(
                    "ALTER TABLE results ADD COLUMN dataset_version TEXT NOT NULL DEFAULT ''"
                )
            if "run_status" not in columns:
                connection.execute(
                    "ALTER TABLE results ADD COLUMN run_status TEXT NOT NULL DEFAULT ''"
                )
