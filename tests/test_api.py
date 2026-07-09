import io
import json
import sqlite3
import tempfile
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


if __name__ == "__main__":
    unittest.main()
