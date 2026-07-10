import html
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from mvp.app import create_app


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.app = create_app({"TESTING": True, "RUNTIME_ROOT": self.root})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _jsonl(records):
        return "".join(
            json.dumps(record, ensure_ascii=False) + "\n" for record in records
        ).encode("utf-8")

    def test_report_escapes_html_from_case_ids_and_notes(self):
        script_case_id = "<script>alert(1)</script>"
        upload = self.client.post(
            "/api/uploads",
            data={
                "model_type": "TTS",
                "cases_file": (
                    io.BytesIO(
                        self._jsonl([
                            {
                                "case_id": script_case_id,
                                "scenario": "xss",
                                "language": "en",
                                "input_text": "hello Alice",
                                "critical_entities": ["Alice"],
                            }
                        ])
                    ),
                    "cases.jsonl",
                ),
                "outputs_file": (
                    io.BytesIO(
                        self._jsonl([
                            {
                                "case_id": script_case_id,
                                "roundtrip_text": "hello Bob",
                            }
                        ])
                    ),
                    "outputs.jsonl",
                ),
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
            if status["report_status"] == "ready":
                break
            time.sleep(0.02)

        report = self.client.get(f"/api/tasks/{task_id}/report")

        self.assertEqual(200, report.status_code)
        html_text = report.get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html_text)
        self.assertIn(html.escape(script_case_id), html_text)

    def test_report_contains_scenario_and_severity_summaries(self):
        upload = self.client.post(
            "/api/uploads",
            data={
                "model_type": "TTS",
                "cases_file": (
                    io.BytesIO(
                        self._jsonl([
                            {
                                "case_id": "TTS-1",
                                "scenario": "confirmation",
                                "language": "en",
                                "input_text": "hello Alice",
                                "critical_entities": ["Alice"],
                            }
                        ])
                    ),
                    "cases.jsonl",
                ),
                "outputs_file": (
                    io.BytesIO(
                        self._jsonl([
                            {
                                "case_id": "TTS-1",
                                "roundtrip_text": "hello Bob",
                            }
                        ])
                    ),
                    "outputs.jsonl",
                ),
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
            if status["report_status"] == "ready":
                break
            time.sleep(0.02)

        report = self.client.get(f"/api/tasks/{task_id}/report")

        self.assertEqual(200, report.status_code)
        html_text = report.get_data(as_text=True)
        self.assertIn("Scenario 汇总", html_text)
        self.assertIn("confirmation", html_text)
        self.assertIn("Severity 汇总", html_text)
        self.assertIn("major", html_text)
        self.assertIn("scorer: mvp-fixture-v0.1", html_text)


if __name__ == "__main__":
    unittest.main()
