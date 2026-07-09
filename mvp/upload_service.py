"""Validate and persist uploaded evaluation datasets."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .ingestion import validate_files
from .storage import Storage


ALLOWED_SUFFIXES = {".jsonl", ".csv"}


def _submitted_basename(filename: str) -> str:
    return secure_filename(Path(filename.replace("\\", "/")).name)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_jsonl(path: Path, records: list) -> None:
    with path.open("w", encoding="utf-8") as target:
        for record in records:
            target.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            )


def persist_upload(
    storage: Storage,
    uploads_root: Path,
    model_type: str,
    cases_file: FileStorage,
    outputs_file: FileStorage,
) -> Dict[str, Any]:
    """Persist a valid upload and return its public validation result."""
    model_type = model_type.upper()
    upload_id = uuid.uuid4().hex
    staging_dir = uploads_root / (".%s.tmp" % upload_id)
    final_dir = uploads_root / upload_id

    submitted_files = (
        ("cases_file", _submitted_basename(cases_file.filename or "")),
        ("outputs_file", _submitted_basename(outputs_file.filename or "")),
    )
    cases_suffix = Path(submitted_files[0][1]).suffix.lower()
    outputs_suffix = Path(submitted_files[1][1]).suffix.lower()
    extension_errors = []
    for field, filename in submitted_files:
        if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
            extension_errors.append({
                "error_code": "INVALID_FILE_TYPE",
                "filename": filename,
                "line": 0,
                "field": field,
                "reason": "file must use .jsonl or .csv",
            })
    if extension_errors:
        return {
            "status": "invalid",
            "error_code": "INVALID_FILE_TYPE",
            "message": "One or more uploaded files have an unsupported type",
            "dataset_version": None,
            "errors": extension_errors,
            "warnings": [],
            "total_records": 0,
            "valid_records": 0,
            "invalid_records": 0,
        }

    staging_dir.mkdir()
    cases_path = staging_dir / ("cases" + cases_suffix)
    outputs_path = staging_dir / ("outputs" + outputs_suffix)
    try:
        cases_file.save(cases_path)
        outputs_file.save(outputs_path)
        validation = validate_files(model_type, cases_path, outputs_path)
        if validation["status"] != "valid":
            public_validation = {
                key: value
                for key, value in validation.items()
                if key not in {"cases", "outputs"}
            }
            first_error = public_validation["errors"][0]
            return {
                **public_validation,
                "error_code": first_error.get("error_code", "UPLOAD_NOT_VALID"),
                "message": first_error.get(
                    "reason", "Uploaded materials did not pass validation"
                ),
                "dataset_version": None,
            }

        cases_checksum = _checksum(cases_path)
        outputs_checksum = _checksum(outputs_path)
        combined_checksum = hashlib.sha256(
            ("cases:" + cases_checksum + "\noutputs:" + outputs_checksum).encode(
                "ascii"
            )
        ).hexdigest()
        created_at = datetime.now(timezone.utc)
        generated_at = created_at.strftime("%Y%m%dT%H%M%S%fZ")
        dataset_version = "%s-%s-%s" % (
            model_type,
            combined_checksum,
            generated_at,
        )
        canonical_cases = staging_dir / "canonical_cases.jsonl"
        canonical_outputs = staging_dir / "canonical_outputs.jsonl"
        _write_jsonl(canonical_cases, validation["cases"])
        _write_jsonl(canonical_outputs, validation["outputs"])
        staging_dir.rename(final_dir)

        timestamp = created_at.isoformat()
        public_validation = {
            key: value
            for key, value in validation.items()
            if key not in {"cases", "outputs"}
        }
        try:
            with storage.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO uploads (
                        upload_id, model_type, cases_path, outputs_path, checksum,
                        status, validation_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        upload_id,
                        model_type,
                        str(final_dir / cases_path.name),
                        str(final_dir / outputs_path.name),
                        combined_checksum,
                        "valid",
                        json.dumps(public_validation, ensure_ascii=False),
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO datasets (
                        dataset_version, upload_id, canonical_cases_path,
                        canonical_outputs_path, sample_count, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset_version,
                        upload_id,
                        str(final_dir / canonical_cases.name),
                        str(final_dir / canonical_outputs.name),
                        validation["valid_records"],
                        timestamp,
                    ),
                )
        except Exception:
            shutil.rmtree(final_dir, ignore_errors=True)
            raise

        return {
            **public_validation,
            "upload_id": upload_id,
            "model_type": model_type,
            "dataset_version": dataset_version,
            "checksum": combined_checksum,
            "checksums": {
                "cases": cases_checksum,
                "outputs": outputs_checksum,
            },
        }
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
