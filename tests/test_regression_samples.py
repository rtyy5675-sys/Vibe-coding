import tempfile
import time
import unittest
from pathlib import Path

from mvp.app import create_app


PACKAGE = Path(__file__).resolve().parents[1] / "sample_packages" / "regression_v0_1"


class RegressionSampleTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "RUNTIME_ROOT": Path(self.temp_dir.name)})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_regression_packages_upload_run_and_generate_reports(self):
        expected = {
            "STT": ("partially_completed", 2),
            "TTS": ("completed", 2),
            "LLM": ("completed", 2),
        }
        for model_type, (expected_status, expected_reviews) in expected.items():
            prefix = model_type.lower()
            with (PACKAGE / f"{prefix}_cases.jsonl").open("rb") as cases_file, (
                PACKAGE / f"{prefix}_outputs.jsonl"
            ).open("rb") as outputs_file:
                upload = self.client.post(
                    "/api/uploads",
                    data={
                        "model_type": model_type,
                        "cases_file": (cases_file, f"{prefix}_cases.jsonl"),
                        "outputs_file": (outputs_file, f"{prefix}_outputs.jsonl"),
                    },
                    content_type="multipart/form-data",
                )
            self.assertEqual(200, upload.status_code, upload.get_data(as_text=True))
            task = self.client.post(
                "/api/tasks",
                json={"upload_id": upload.get_json()["upload_id"], "runner_mode": "fixture"},
            )
            self.assertEqual(202, task.status_code, task.get_data(as_text=True))
            task_id = task.get_json()["task_id"]
            for _ in range(50):
                status = self.client.get(f"/api/tasks/{task_id}").get_json()
                if status["status"] in {"completed", "partially_completed", "failed"}:
                    break
                time.sleep(0.02)
            self.assertEqual(expected_status, status["status"])
            self.assertEqual("ready", status["report_status"])
            self.assertEqual(expected_reviews, status["counts"]["review_required"])
            self.assertEqual(200, self.client.get(f"/api/tasks/{task_id}/report").status_code)


if __name__ == "__main__":
    unittest.main()
