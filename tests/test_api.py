import io
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mvp.app import create_app


class UploadApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.app = create_app({"TESTING": True, "RUNTIME_ROOT": self.root})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def valid_stt_upload(cases_name="cases.jsonl", outputs_name="outputs.jsonl"):
        cases = {
            "case_id": "STT-1",
            "scenario": "support",
            "language": "en",
            "reference_text": "hello",
            "critical_entities": [],
        }
        outputs = {"case_id": "STT-1", "prediction": "hello"}
        return {
            "model_type": "STT",
            "cases_file": (
                io.BytesIO((json.dumps(cases) + "\n").encode("utf-8")),
                cases_name,
            ),
            "outputs_file": (
                io.BytesIO((json.dumps(outputs) + "\n").encode("utf-8")),
                outputs_name,
            ),
        }

    def test_valid_upload_persists_sanitized_originals_and_frozen_dataset(self):
        response = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload("../cases.jsonl", "nested/outputs.jsonl"),
            content_type="multipart/form-data",
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("valid", payload["status"])
        self.assertEqual("STT", payload["model_type"])
        self.assertEqual({"cases", "outputs"}, set(payload["checksums"]))
        self.assertRegex(
            payload["dataset_version"],
            r"^STT-[0-9a-f]{64}-\d{8}T\d{6}\d{6}Z$",
        )
        upload_dir = self.root / "uploads" / payload["upload_id"]
        self.assertEqual(
            {
                "cases.jsonl",
                "outputs.jsonl",
                "canonical_cases.jsonl",
                "canonical_outputs.jsonl",
            },
            {path.name for path in upload_dir.iterdir()},
        )
        canonical_output = json.loads(
            (upload_dir / "canonical_outputs.jsonl").read_text(encoding="utf-8")
        )
        self.assertEqual("hello", canonical_output["transcript"])

        with sqlite3.connect(self.root / "data" / "eval_mvp.sqlite") as connection:
            upload_count = connection.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]
            dataset_count = connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        self.assertEqual(1, upload_count)
        self.assertEqual(1, dataset_count)

    def test_valid_upload_accepts_non_ascii_jsonl_filenames(self):
        response = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload("案例.jsonl", "输出.jsonl"),
            content_type="multipart/form-data",
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("valid", payload["status"])
        upload_dir = self.root / "uploads" / payload["upload_id"]
        self.assertEqual(
            {
                "cases.jsonl",
                "outputs.jsonl",
                "canonical_cases.jsonl",
                "canonical_outputs.jsonl",
            },
            {path.name for path in upload_dir.iterdir()},
        )

    def test_valid_upload_accepts_non_ascii_csv_filenames(self):
        cases_csv = (
            "case_id,scenario,language,reference_text,critical_entities\n"
            "STT-1,support,en,hello,[]\n"
        )
        outputs_csv = "case_id,prediction\nSTT-1,hello\n"

        response = self.client.post(
            "/api/uploads",
            data={
                "model_type": "STT",
                "cases_file": (io.BytesIO(cases_csv.encode("utf-8")), "案例.csv"),
                "outputs_file": (io.BytesIO(outputs_csv.encode("utf-8")), "输出.csv"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("valid", payload["status"])
        upload_dir = self.root / "uploads" / payload["upload_id"]
        saved_names = {path.name for path in upload_dir.iterdir()}
        self.assertIn("cases.csv", saved_names)
        self.assertIn("outputs.csv", saved_names)

    def test_invalid_upload_returns_stable_error_and_creates_no_dataset(self):
        upload = self.valid_stt_upload()
        upload["cases_file"] = (io.BytesIO(b'{"broken":\n'), "cases.jsonl")

        response = self.client.post(
            "/api/uploads", data=upload, content_type="multipart/form-data"
        )

        self.assertEqual(422, response.status_code)
        payload = response.get_json()
        self.assertEqual("invalid", payload["status"])
        self.assertEqual("INVALID_JSON", payload["error_code"])
        self.assertTrue(payload["message"])
        self.assertIsNone(payload["dataset_version"])
        self.assertEqual(
            {"error_code", "filename", "line", "field", "reason"},
            set(payload["errors"][0]),
        )
        self.assertEqual([], list((self.root / "uploads").iterdir()))
        with sqlite3.connect(self.root / "data" / "eval_mvp.sqlite") as connection:
            upload_count = connection.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]
            dataset_count = connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        self.assertEqual(0, upload_count)
        self.assertEqual(0, dataset_count)

    def test_missing_multipart_fields_returns_stable_request_error(self):
        response = self.client.post(
            "/api/uploads",
            data={"model_type": "STT"},
            content_type="multipart/form-data",
        )

        self.assertEqual(400, response.status_code)
        self.assertEqual(
            {
                "status": "invalid",
                "error_code": "MISSING_FIELD",
                "message": "model_type, cases_file and outputs_file are required",
                "dataset_version": None,
                "errors": [],
            },
            response.get_json(),
        )

    def test_invalid_extensions_report_each_offending_sanitized_filename(self):
        examples = (
            ("cases.txt", "outputs.jsonl", ["cases.txt"]),
            ("cases.jsonl", "../outputs.exe", ["outputs.exe"]),
            ("../cases.txt", "nested/outputs.exe", ["cases.txt", "outputs.exe"]),
        )
        for cases_name, outputs_name, expected_names in examples:
            with self.subTest(cases=cases_name, outputs=outputs_name):
                response = self.client.post(
                    "/api/uploads",
                    data=self.valid_stt_upload(cases_name, outputs_name),
                    content_type="multipart/form-data",
                )

                self.assertEqual(422, response.status_code)
                payload = response.get_json()
                self.assertEqual("INVALID_FILE_TYPE", payload["error_code"])
                self.assertTrue(payload["message"])
                self.assertEqual(
                    expected_names,
                    [error["filename"] for error in payload["errors"]],
                )
                self.assertTrue(
                    all(
                        error["error_code"] == "INVALID_FILE_TYPE"
                        for error in payload["errors"]
                    )
                )

    def test_unexpected_upload_failure_uses_safe_internal_error_envelope(self):
        with patch("mvp.app.persist_upload", side_effect=RuntimeError("secret input")):
            response = self.client.post(
                "/api/uploads",
                data=self.valid_stt_upload(),
                content_type="multipart/form-data",
            )

        self.assertEqual(500, response.status_code)
        payload = response.get_json()
        self.assertEqual("INTERNAL_ERROR", payload["error_code"])
        self.assertNotIn("secret input", response.get_data(as_text=True))
        self.assertEqual([], payload["errors"])

    def test_unknown_api_route_returns_http_error_envelope(self):
        response = self.client.get("/api/not-found")

        self.assertEqual(404, response.status_code)
        payload = response.get_json()
        self.assertEqual("error", payload["status"])
        self.assertEqual("NOT_FOUND", payload["error_code"])
        self.assertTrue(payload["message"])
        self.assertEqual([], payload["errors"])

    def test_wrong_api_method_returns_http_error_envelope(self):
        response = self.client.get("/api/uploads")

        self.assertEqual(405, response.status_code)
        payload = response.get_json()
        self.assertEqual("error", payload["status"])
        self.assertEqual("METHOD_NOT_ALLOWED", payload["error_code"])
        self.assertTrue(payload["message"])
        self.assertEqual([], payload["errors"])

    def test_index_contains_upload_controls_and_disabled_task_gate(self):
        response = self.client.get("/")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn('name="model_type"', html)
        self.assertIn('name="cases_file"', html)
        self.assertIn('name="outputs_file"', html)
        self.assertRegex(html, r'<button[^>]+id="create-task"[^>]+disabled')
        self.assertIn('id="upload-errors"', html)
        self.assertIn('id="upload-warnings"', html)
        javascript = (Path(self.app.static_folder) / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('payload.warnings', javascript)
        self.assertIn('upload-warnings', javascript)

    def test_index_exposes_create_task_controls_and_recent_tasks(self):
        response = self.client.get("/")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn('id="create-task"', html)
        self.assertIn('id="task-status"', html)
        self.assertIn('id="recent-tasks"', html)
        javascript = (Path(self.app.static_folder) / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('fetch("/api/tasks"', javascript)
        self.assertIn("currentUploadId", javascript)

    def test_task_detail_page_shows_status_and_report_links(self):
        upload_response = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload(),
            content_type="multipart/form-data",
        )
        upload_id = upload_response.get_json()["upload_id"]
        task_response = self.client.post(
            "/api/tasks",
            json={"upload_id": upload_id, "runner_mode": "fixture"},
        )
        self.assertEqual("queued", task_response.get_json()["status"])
        task_id = task_response.get_json()["task_id"]
        for _ in range(50):
            task_status = self.client.get(f"/api/tasks/{task_id}").get_json()
            if task_status["report_status"] == "ready":
                break
            time.sleep(0.02)

        response = self.client.get(f"/tasks/{task_id}")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn(task_id, html)
        self.assertIn("report", html)
        self.assertIn("results.csv", html)
        self.assertIn("/retry", html)

    def test_task_detail_page_refreshes_in_progress_tasks_and_hides_completed_retry(self):
        upload_response = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload(),
            content_type="multipart/form-data",
        )
        task_response = self.client.post(
            "/api/tasks",
            json={
                "upload_id": upload_response.get_json()["upload_id"],
                "runner_mode": "fixture",
            },
        )
        task_id = task_response.get_json()["task_id"]
        for _ in range(50):
            status = self.client.get(f"/api/tasks/{task_id}").get_json()
            if status["status"] == "completed":
                break
            time.sleep(0.02)

        response = self.client.get(f"/tasks/{task_id}")

        self.assertNotIn('id="retry-task"', response.get_data(as_text=True))
        template = (Path(self.app.template_folder) / "task.html").read_text(encoding="utf-8")
        self.assertIn("window.setTimeout", template)

    def test_missing_ready_report_file_returns_report_not_ready(self):
        upload_response = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload(),
            content_type="multipart/form-data",
        )
        task_response = self.client.post(
            "/api/tasks",
            json={
                "upload_id": upload_response.get_json()["upload_id"],
                "runner_mode": "fixture",
            },
        )
        task_id = task_response.get_json()["task_id"]
        for _ in range(50):
            status = self.client.get(f"/api/tasks/{task_id}").get_json()
            if status["report_status"] == "ready":
                break
            time.sleep(0.02)
        Path(status["report_path"]).unlink()

        response = self.client.get(f"/api/tasks/{task_id}/report")

        self.assertEqual(404, response.status_code)
        self.assertEqual("REPORT_NOT_READY", response.get_json()["error_code"])

        retry = self.client.post(f"/api/tasks/{task_id}/report/retry")
        self.assertEqual(202, retry.status_code)
        for _ in range(50):
            refreshed = self.client.get(f"/api/tasks/{task_id}").get_json()
            if refreshed["report_status"] == "ready":
                break
            time.sleep(0.02)
        self.assertEqual("ready", refreshed["report_status"])
        self.assertEqual(200, self.client.get(f"/api/tasks/{task_id}/report").status_code)

    def test_missing_task_detail_page_returns_404(self):
        response = self.client.get("/tasks/task_missing")

        self.assertEqual(404, response.status_code)

    def test_report_api_errors_use_stable_envelope(self):
        for path in (
            "/api/tasks/task_missing/report",
            "/api/tasks/task_missing/results.csv",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertEqual(404, response.status_code)
                self.assertEqual(
                    {
                        "status": "invalid",
                        "error_code": "TASK_NOT_FOUND",
                        "message": "task_id does not exist",
                        "errors": [],
                    },
                    response.get_json(),
                )

    def test_retry_completed_task_returns_invalid_state_transition(self):
        upload_response = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload(),
            content_type="multipart/form-data",
        )
        task_response = self.client.post(
            "/api/tasks",
            json={
                "upload_id": upload_response.get_json()["upload_id"],
                "runner_mode": "fixture",
            },
        )
        task_id = task_response.get_json()["task_id"]
        for _ in range(50):
            status = self.client.get(f"/api/tasks/{task_id}").get_json()
            if status["status"] == "completed":
                break
            time.sleep(0.02)

        response = self.client.post(f"/api/tasks/{task_id}/retry")

        self.assertEqual(409, response.status_code)
        self.assertEqual(
            {
                "status": "invalid",
                "error_code": "INVALID_STATE_TRANSITION",
                "message": "task cannot be retried from completed",
                "errors": [],
            },
            response.get_json(),
        )

    def test_index_lists_recent_task_after_creation(self):
        upload_response = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload(),
            content_type="multipart/form-data",
        )
        task_response = self.client.post(
            "/api/tasks",
            json={
                "upload_id": upload_response.get_json()["upload_id"],
                "runner_mode": "fixture",
            },
        )
        task_id = task_response.get_json()["task_id"]
        for _ in range(50):
            status = self.client.get(f"/api/tasks/{task_id}").get_json()
            if status["status"] in {"completed", "partially_completed", "failed"}:
                break
            time.sleep(0.02)

        response = self.client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertIn(task_id, response.get_data(as_text=True))

    def test_api_acceptance_probe_for_platform_gaps(self):
        upload = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload("案例.jsonl", "输出.jsonl"),
            content_type="multipart/form-data",
        )
        self.assertEqual(200, upload.status_code)
        self.assertEqual(404, self.client.get("/api/not-found").status_code)
        self.assertEqual(405, self.client.get("/api/uploads").status_code)


if __name__ == "__main__":
    unittest.main()
