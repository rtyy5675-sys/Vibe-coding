import tempfile
import unittest
from pathlib import Path

from mvp.app import create_app
from mvp.storage import Storage


class AppStartupTests(unittest.TestCase):
    def test_factory_creates_runtime_directories_and_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            app = create_app({"TESTING": True, "RUNTIME_ROOT": root})

            self.assertTrue(app.testing)
            self.assertTrue((root / "data" / "eval_mvp.sqlite").is_file())
            for relative_path in ("uploads", "runs", "reports/generated"):
                self.assertTrue((root / relative_path).is_dir())

    def test_factory_marks_interrupted_running_items_as_retryable_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            create_app({"TESTING": True, "RUNTIME_ROOT": root})
            storage = Storage(root / "data" / "eval_mvp.sqlite")
            with storage.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO uploads VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("upl-1", "STT", "cases", "outputs", "checksum", "valid", "{}", "now"),
                )
                connection.execute(
                    """
                    INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("dataset-1", "upl-1", "cases", "outputs", 1, "now"),
                )
                connection.execute(
                    """
                    INSERT INTO tasks (
                        task_id, dataset_version, model_type, runner_mode, status,
                        scorer_version, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("task-1", "dataset-1", "STT", "fixture", "running", "v", "now"),
                )
                connection.execute(
                    """
                    INSERT INTO task_items (
                        task_id, case_id, status, attempt_count
                    ) VALUES (?, ?, ?, ?)
                    """,
                    ("task-1", "case-1", "running", 1),
                )

            create_app({"TESTING": True, "RUNTIME_ROOT": root})

            with storage.connect() as connection:
                item = connection.execute(
                    "SELECT status, error_message FROM task_items WHERE task_id = 'task-1'"
                ).fetchone()
                task_status = connection.execute(
                    "SELECT status FROM tasks WHERE task_id = 'task-1'"
                ).fetchone()[0]
            self.assertEqual(("failed", "interrupted before completion"), item)
            self.assertEqual("failed", task_status)


if __name__ == "__main__":
    unittest.main()
