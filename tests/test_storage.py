import sqlite3
import tempfile
import unittest
from pathlib import Path

from mvp.storage import Storage


class StorageTests(unittest.TestCase):
    def test_initialization_creates_spec_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "eval.sqlite"
            Storage(database).initialize()

            with sqlite3.connect(database) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }

        self.assertTrue(
            {"uploads", "datasets", "tasks", "task_items", "results", "reports"}
            <= tables
        )

    def test_task_items_has_composite_primary_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "eval.sqlite")
            storage.initialize()
            with storage.connect() as connection:
                primary_key = [
                    row[1]
                    for row in connection.execute("PRAGMA table_info(task_items)")
                    if row[5]
                ]

        self.assertEqual(["task_id", "case_id"], primary_key)

    def test_storage_connect_enforces_foreign_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "eval.sqlite")
            storage.initialize()

            with storage.connect() as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO datasets (
                            dataset_version, upload_id, canonical_cases_path,
                            canonical_outputs_path, sample_count, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        ("v1", "missing", "cases", "outputs", 1, "now"),
                    )


if __name__ == "__main__":
    unittest.main()
