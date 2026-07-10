#!/usr/bin/env python3
"""Run the local MVP through upload, task creation, scoring, and report checks."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "sample_packages"


def request_json(url: str, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None):
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def upload(base_url: str, model_type: str, cases_path: Path, outputs_path: Path) -> str:
    boundary = "----evalmvp" + uuid.uuid4().hex
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(value.encode("utf-8") + b"\r\n")

    def add_file(name: str, path: Path) -> None:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode("utf-8")
        )
        body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
        body.extend(path.read_bytes() + b"\r\n")

    add_field("model_type", model_type)
    add_file("cases_file", cases_path)
    add_file("outputs_file", outputs_path)
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    status, payload = request_json(
        base_url.rstrip("/") + "/api/uploads",
        method="POST",
        body=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if status != 200 or payload.get("status") != "valid":
        raise RuntimeError(f"{model_type} upload failed: {payload}")
    return payload["upload_id"]


def create_task(base_url: str, upload_id: str) -> str:
    status, payload = request_json(
        base_url.rstrip("/") + "/api/tasks",
        method="POST",
        body=json.dumps({"upload_id": upload_id, "runner_mode": "fixture"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    if status != 202:
        raise RuntimeError(f"task creation failed: {payload}")
    return payload["task_id"]


def wait_for_report(base_url: str, task_id: str) -> None:
    for _ in range(60):
        status, payload = request_json(base_url.rstrip("/") + f"/api/tasks/{task_id}")
        if status == 200 and payload["status"] in {"completed", "partially_completed"}:
            if payload["report_status"] == "ready":
                return
        time.sleep(0.2)
    raise RuntimeError(f"task did not produce a report: {task_id}")


def check_report(base_url: str, task_id: str) -> None:
    for suffix in ("report", "results.csv"):
        request = urllib.request.Request(base_url.rstrip("/") + f"/api/tasks/{task_id}/{suffix}")
        with urllib.request.urlopen(request, timeout=10) as response:
            content = response.read()
            if response.status != 200 or not content:
                raise RuntimeError(f"{suffix} not available for {task_id}")


def check_task_page(base_url: str, task_id: str) -> None:
    request = urllib.request.Request(base_url.rstrip("/") + f"/tasks/{task_id}")
    with urllib.request.urlopen(request, timeout=10) as response:
        content = response.read().decode("utf-8")
        if response.status != 200 or task_id not in content or "results.csv" not in content:
            raise RuntimeError(f"task page not available for {task_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8766")
    args = parser.parse_args(argv)

    try:
        for model_type in ("STT", "TTS", "LLM"):
            prefix = model_type.lower()
            upload_id = upload(
                args.base_url,
                model_type,
                SAMPLES / f"{prefix}_cases.jsonl",
                SAMPLES / f"{prefix}_outputs.jsonl",
            )
            task_id = create_task(args.base_url, upload_id)
            wait_for_report(args.base_url, task_id)
            check_report(args.base_url, task_id)
            check_task_page(args.base_url, task_id)
    except (RuntimeError, urllib.error.URLError) as exc:
        print(f"Smoke test: failed: {exc}", file=sys.stderr)
        return 1

    print("Smoke test: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
