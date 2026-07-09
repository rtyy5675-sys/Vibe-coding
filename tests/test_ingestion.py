import json
import tempfile
import unittest
from pathlib import Path

from mvp.ingestion import validate_files


class ValidateFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_jsonl(self, name, records):
        path = self.root / name
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )
        return path

    def test_valid_stt_files_are_canonicalized(self):
        cases = self.write_jsonl(
            "cases.jsonl",
            [{
                "case_id": "STT-1",
                "scenario": "support",
                "language": "id-ID",
                "reference_text": "hello",
                "critical_entities": [],
            }],
        )
        outputs = self.write_jsonl(
            "outputs.jsonl", [{"case_id": "STT-1", "prediction": "hello"}]
        )

        result = validate_files("STT", cases, outputs)

        self.assertEqual("valid", result["status"])
        self.assertEqual(1, result["total_records"])
        self.assertEqual("hello", result["outputs"][0]["transcript"])
        self.assertEqual([], result["errors"])

    def test_duplicate_case_id_is_rejected(self):
        record = {
            "case_id": "STT-1",
            "scenario": "support",
            "language": "id-ID",
            "reference_text": "hello",
            "critical_entities": [],
        }
        cases = self.write_jsonl("cases.jsonl", [record, record])
        outputs = self.write_jsonl("outputs.jsonl", [])

        result = validate_files("STT", cases, outputs)

        self.assertEqual("invalid", result["status"])
        self.assertEqual("DUPLICATE_CASE_ID", result["errors"][0]["error_code"])
        self.assertEqual(2, result["errors"][0]["line"])

    def test_duplicate_output_case_id_is_rejected_and_not_canonicalized_twice(self):
        cases = self.write_jsonl(
            "cases.jsonl",
            [{
                "case_id": "STT-1",
                "scenario": "support",
                "language": "en",
                "reference_text": "hello",
                "critical_entities": [],
            }],
        )
        outputs = self.write_jsonl(
            "outputs.jsonl",
            [
                {"case_id": "STT-1", "transcript": "first"},
                {"case_id": "STT-1", "transcript": "second"},
            ],
        )

        result = validate_files("STT", cases, outputs)

        duplicate = next(
            error
            for error in result["errors"]
            if error["error_code"] == "DUPLICATE_CASE_ID"
        )
        self.assertEqual("invalid", result["status"])
        self.assertEqual("outputs.jsonl", duplicate["filename"])
        self.assertEqual(2, duplicate["line"])
        self.assertEqual("case_id", duplicate["field"])
        self.assertEqual(1, len(result["outputs"]))

    def test_duplicate_unknown_output_ids_remain_warnings(self):
        cases = self.write_jsonl(
            "cases.jsonl",
            [{
                "case_id": "STT-1",
                "scenario": "support",
                "language": "en",
                "reference_text": "hello",
                "critical_entities": [],
            }],
        )
        outputs = self.write_jsonl(
            "outputs.jsonl",
            [
                {"case_id": "OTHER", "transcript": "first"},
                {"case_id": "OTHER", "transcript": "second"},
            ],
        )

        result = validate_files("STT", cases, outputs)

        self.assertEqual("valid", result["status"])
        self.assertEqual([], result["errors"])
        self.assertEqual(
            ["UNKNOWN_OUTPUT_CASE_ID", "UNKNOWN_OUTPUT_CASE_ID", "MISSING_OUTPUT"],
            [warning["error_code"] for warning in result["warnings"]],
        )
        self.assertEqual([], result["outputs"])

    def test_missing_required_field_has_stable_error(self):
        cases = self.write_jsonl("cases.jsonl", [{"case_id": "LLM-1"}])
        outputs = self.write_jsonl("outputs.jsonl", [])

        result = validate_files("LLM", cases, outputs)

        self.assertEqual("invalid", result["status"])
        self.assertTrue(
            any(
                error["error_code"] == "MISSING_FIELD"
                and error["field"] == "task_type"
                for error in result["errors"]
            )
        )

    def test_unknown_and_missing_outputs_are_warnings(self):
        cases = self.write_jsonl(
            "cases.jsonl",
            [{
                "case_id": "TTS-1",
                "scenario": "support",
                "language": "id-ID",
                "input_text": "hello",
                "critical_entities": [],
            }],
        )
        outputs = self.write_jsonl(
            "outputs.jsonl", [{"case_id": "OTHER", "roundtrip_text": "hello"}]
        )

        result = validate_files("TTS", cases, outputs)

        self.assertEqual("valid", result["status"])
        self.assertEqual(
            {"UNKNOWN_OUTPUT_CASE_ID", "MISSING_OUTPUT"},
            {warning["error_code"] for warning in result["warnings"]},
        )
        missing = next(
            warning
            for warning in result["warnings"]
            if warning["error_code"] == "MISSING_OUTPUT"
        )
        self.assertEqual("cases.jsonl", missing["filename"])
        self.assertEqual(1, missing["line"])

    def test_malformed_and_non_object_cases_are_counted_as_invalid_records(self):
        cases = self.root / "cases.jsonl"
        cases.write_text('{"broken":\n[]\n', encoding="utf-8")
        outputs = self.write_jsonl("outputs.jsonl", [])

        result = validate_files("STT", cases, outputs)

        self.assertEqual(2, result["total_records"])
        self.assertEqual(0, result["valid_records"])
        self.assertEqual(2, result["invalid_records"])
        self.assertEqual(
            result["total_records"],
            result["valid_records"] + result["invalid_records"],
        )
        self.assertEqual(
            {"INVALID_JSON", "INVALID_RECORD"},
            {error["error_code"] for error in result["errors"]},
        )

    def test_invalid_file_and_model_types_have_stable_errors(self):
        cases = self.root / "cases.txt"
        cases.write_text("", encoding="utf-8")
        outputs = self.write_jsonl("outputs.jsonl", [])

        file_result = validate_files("STT", cases, outputs)
        model_result = validate_files("vision", cases, outputs)

        self.assertEqual("INVALID_FILE_TYPE", file_result["errors"][0]["error_code"])
        self.assertEqual("invalid", model_result["status"])
        self.assertEqual("INVALID_MODEL_TYPE", model_result["errors"][0]["error_code"])

    def test_whitespace_only_case_ids_are_rejected_in_jsonl_and_csv(self):
        jsonl_cases = self.write_jsonl(
            "cases.jsonl",
            [{
                "case_id": "  ",
                "scenario": "support",
                "language": "en",
                "reference_text": "hello",
                "critical_entities": [],
            }],
        )
        csv_cases = self.root / "cases.csv"
        csv_cases.write_text(
            "case_id,scenario,language,reference_text,critical_entities\n"
            '"   ",support,en,hello,[]\n',
            encoding="utf-8",
        )
        outputs = self.write_jsonl("outputs.jsonl", [])

        for cases in (jsonl_cases, csv_cases):
            with self.subTest(cases=cases.name):
                result = validate_files("STT", cases, outputs)
                self.assertTrue(
                    any(
                        error["error_code"] == "MISSING_FIELD"
                        and error["field"] == "case_id"
                        for error in result["errors"]
                    )
                )

    def test_csv_rejects_blank_duplicate_headers_and_bad_quoting(self):
        outputs = self.write_jsonl("outputs.jsonl", [])
        examples = {
            "blank.csv": ",scenario\nA,support\n",
            "duplicate.csv": "case_id,case_id\nA,B\n",
            "quote.csv": 'case_id,scenario\n"A,support\n',
        }

        for name, content in examples.items():
            with self.subTest(name=name):
                cases = self.root / name
                cases.write_text(content, encoding="utf-8")
                result = validate_files("STT", cases, outputs)
                self.assertTrue(
                    any(
                        error["error_code"] == "INVALID_CSV"
                        for error in result["errors"]
                    )
                )

    def test_invalid_utf8_is_rejected(self):
        cases = self.root / "cases.jsonl"
        cases.write_bytes(b"\xff\n")
        outputs = self.write_jsonl("outputs.jsonl", [])

        result = validate_files("STT", cases, outputs)

        self.assertEqual("INVALID_ENCODING", result["errors"][0]["error_code"])

    def test_required_types_and_present_output_fields_are_validated(self):
        cases = self.write_jsonl(
            "cases.jsonl",
            [{
                "case_id": "STT-1",
                "scenario": "support",
                "language": "en",
                "reference_text": "hello",
                "critical_entities": {},
            }],
        )
        outputs = self.write_jsonl("outputs.jsonl", [{"case_id": "STT-1"}])

        result = validate_files("STT", cases, outputs)

        self.assertTrue(
            any(
                error["error_code"] == "INVALID_TYPE"
                and error["field"] == "critical_entities"
                for error in result["errors"]
            )
        )
        self.assertTrue(
            any(
                error["error_code"] == "MISSING_FIELD"
                and error["field"] == "transcript"
                for error in result["errors"]
            )
        )

    def test_all_stt_aliases_and_llm_object_output_are_accepted(self):
        for alias in ("prediction", "predicted_text", "output_text"):
            with self.subTest(alias=alias):
                cases = self.write_jsonl(
                    f"{alias}-cases.jsonl",
                    [{
                        "case_id": "STT-1",
                        "scenario": "support",
                        "language": "en",
                        "reference_text": "hello",
                        "critical_entities": [],
                    }],
                )
                outputs = self.write_jsonl(
                    f"{alias}-outputs.jsonl",
                    [{"case_id": "STT-1", alias: "hello"}],
                )
                self.assertEqual("valid", validate_files("STT", cases, outputs)["status"])

        llm_cases = self.write_jsonl(
            "llm-cases.jsonl",
            [{
                "case_id": "LLM-1",
                "task_type": "qa",
                "input": "question",
                "expected": {},
                "assertions": [],
            }],
        )
        llm_outputs = self.write_jsonl(
            "llm-outputs.jsonl",
            [{"case_id": "LLM-1", "output": {"answer": "yes"}}],
        )
        self.assertEqual(
            "valid", validate_files("LLM", llm_cases, llm_outputs)["status"]
        )

    def test_csv_json_fields_are_decoded(self):
        cases = self.root / "cases.csv"
        cases.write_text(
            "case_id,scenario,language,input_text,critical_entities\n"
            'TTS-1,support,en,hello,"[""name""]"\n',
            encoding="utf-8",
        )
        outputs = self.root / "outputs.csv"
        outputs.write_text(
            "case_id,roundtrip_text\nTTS-1,hello\n",
            encoding="utf-8",
        )

        result = validate_files("TTS", cases, outputs)

        self.assertEqual("valid", result["status"])
        self.assertEqual(["name"], result["cases"][0]["critical_entities"])


if __name__ == "__main__":
    unittest.main()
