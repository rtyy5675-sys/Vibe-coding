import json
import io
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from mvp.app import create_app
from mvp.pipeline import create_task, run_task
from mvp.storage import Storage


class PipelineApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.app = create_app({"TESTING": True, "RUNTIME_ROOT": self.root})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _jsonl_bytes(records):
        payload = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
        return payload.encode("utf-8")

    def _upload(self, model_type, cases, outputs):
        response = self.client.post(
            "/api/uploads",
            data={
                "model_type": model_type,
                "cases_file": (io.BytesIO(self._jsonl_bytes(cases)), "cases.jsonl"),
                "outputs_file": (io.BytesIO(self._jsonl_bytes(outputs)), "outputs.jsonl"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(200, response.status_code, response.get_data(as_text=True))
        return response.get_json()

    def _create_and_wait(self, upload_id):
        response = self.client.post(
            "/api/tasks",
            json={"upload_id": upload_id, "runner_mode": "fixture"},
        )
        self.assertEqual(202, response.status_code, response.get_data(as_text=True))
        task_id = response.get_json()["task_id"]
        for _ in range(50):
            status = self.client.get(f"/api/tasks/{task_id}").get_json()
            if status["status"] in {"completed", "partially_completed", "failed"}:
                return status
            time.sleep(0.02)
        self.fail("task did not finish")

    def test_stt_task_scores_results_and_generates_report_files(self):
        upload = self._upload(
            "STT",
            [{
                "case_id": "STT-1",
                "scenario": "support",
                "language": "en",
                "reference_text": "hello world",
                "critical_entities": ["world"],
            }],
            [{"case_id": "STT-1", "transcript": "hello world"}],
        )

        status = self._create_and_wait(upload["upload_id"])

        self.assertEqual("completed", status["status"])
        self.assertEqual(100, status["progress"])
        self.assertEqual(1, status["counts"]["succeeded"])
        self.assertEqual("ready", status["report_status"])
        report_path = self.root / "reports/generated" / status["task_id"] / "report.html"
        csv_path = self.root / "reports/generated" / status["task_id"] / "results.csv"
        self.assertTrue(report_path.is_file())
        self.assertTrue(csv_path.is_file())
        csv_text = csv_path.read_text(encoding="utf-8")
        self.assertIn("wer", csv_text)
        self.assertIn("entity_score", csv_text)
        self.assertIn("entity_pass", csv_text)

    def test_missing_output_becomes_failed_and_retry_does_not_rerun_success(self):
        upload = self._upload(
            "TTS",
            [
                {
                    "case_id": "TTS-1",
                    "scenario": "confirmation",
                    "language": "en",
                    "input_text": "hello Alice",
                    "critical_entities": ["Alice"],
                    "human_review_required": True,
                },
                {
                    "case_id": "TTS-2",
                    "scenario": "confirmation",
                    "language": "en",
                    "input_text": "hello Bob",
                    "critical_entities": ["Bob"],
                },
            ],
            [{"case_id": "TTS-1", "roundtrip_text": "hello Alice"}],
        )
        status = self._create_and_wait(upload["upload_id"])
        self.assertEqual("partially_completed", status["status"])
        self.assertEqual(1, status["counts"]["succeeded"])
        self.assertEqual(1, status["counts"]["failed"])
        self.assertEqual(2, status["counts"]["review_required"])

        with sqlite3.connect(self.root / "data" / "eval_mvp.sqlite") as connection:
            before = dict(
                connection.execute(
                    "SELECT case_id, attempt_count FROM task_items WHERE task_id = ?",
                    (status["task_id"],),
                ).fetchall()
            )

        retry = self.client.post(f"/api/tasks/{status['task_id']}/retry")
        self.assertEqual(202, retry.status_code)
        for _ in range(50):
            status_after_retry = self.client.get(f"/api/tasks/{status['task_id']}").get_json()
            if status_after_retry["status"] in {"completed", "partially_completed", "failed"}:
                break
            time.sleep(0.02)
        self.assertEqual("partially_completed", status_after_retry["status"])

        with sqlite3.connect(self.root / "data" / "eval_mvp.sqlite") as connection:
            after = dict(
                connection.execute(
                    "SELECT case_id, attempt_count FROM task_items WHERE task_id = ?",
                    (status["task_id"],),
                ).fetchall()
            )
        self.assertEqual(before["TTS-1"], after["TTS-1"])
        self.assertGreater(after["TTS-2"], before["TTS-2"])

    def test_llm_task_scores_rule_assertions(self):
        upload = self._upload(
            "LLM",
            [{
                "case_id": "LLM-1",
                "task_type": "extract",
                "input": "Return the order id.",
                "expected": {"order_id": "INV-1"},
                "assertions": ["valid_json", "contains_required_fields", "exact_match_entities"],
            }],
            [{"case_id": "LLM-1", "output": {"order_id": "INV-1"}}],
        )

        status = self._create_and_wait(upload["upload_id"])

        self.assertEqual("completed", status["status"])
        report = self.client.get(f"/api/tasks/{status['task_id']}/report")
        self.assertEqual(200, report.status_code)
        self.assertIn("valid_json", report.get_data(as_text=True))

    def test_llm_empty_forbidden_steps_passes(self):
        upload = self._upload(
            "LLM",
            [{
                "case_id": "LLM-1",
                "task_type": "safety",
                "input": "Provide a safe answer.",
                "expected": {"forbidden_steps": []},
                "assertions": ["does_not_contain_forbidden_steps"],
            }],
            [{"case_id": "LLM-1", "output": "Use the documented process."}],
        )

        status = self._create_and_wait(upload["upload_id"])

        self.assertEqual("completed", status["status"])
        report = self.client.get(f"/api/tasks/{status['task_id']}/results.csv")
        self.assertIn("does_not_contain_forbidden_steps", report.get_data(as_text=True))
        self.assertIn(",1.0,", report.get_data(as_text=True))
        report.close()

    def test_concurrent_runners_claim_each_item_once(self):
        cases = [
            {
                "case_id": f"STT-{index}",
                "scenario": "support",
                "language": "en",
                "reference_text": "hello world",
                "critical_entities": ["world"],
            }
            for index in range(1, 6)
        ]
        outputs = [
            {"case_id": case["case_id"], "transcript": "hello world"}
            for case in cases
        ]
        upload = self._upload("STT", cases, outputs)
        storage = Storage(self.root / "data" / "eval_mvp.sqlite")
        task = create_task(storage, self.root, upload["upload_id"], "fixture")
        task_id = task["task_id"]

        threads = [
            threading.Thread(target=run_task, args=(storage, self.root, task_id, False))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        with sqlite3.connect(self.root / "data" / "eval_mvp.sqlite") as connection:
            attempts = [
                row[0]
                for row in connection.execute(
                    "SELECT attempt_count FROM task_items WHERE task_id = ?",
                    (task_id,),
                )
            ]

        self.assertEqual([1, 1, 1, 1, 1], sorted(attempts))


if __name__ == "__main__":
    unittest.main()
