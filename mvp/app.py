"""Flask application factory for the evaluation MVP."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

from .pipeline import create_task, get_task, retry_task
from .storage import Storage
from .upload_service import persist_upload


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(config=None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config.from_mapping(RUNTIME_ROOT=PROJECT_ROOT)
    if config:
        app.config.update(config)

    runtime_root = Path(app.config["RUNTIME_ROOT"])
    for relative_path in ("data", "uploads", "runs", "reports/generated"):
        (runtime_root / relative_path).mkdir(parents=True, exist_ok=True)
    storage = Storage(runtime_root / "data" / "eval_mvp.sqlite")
    storage.initialize()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.errorhandler(Exception)
    def internal_error(_error):
        return jsonify({
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred while processing the request",
            "errors": [],
        }), 500

    @app.post("/api/uploads")
    def upload():
        model_type = request.form.get("model_type", "").strip()
        cases_file = request.files.get("cases_file")
        outputs_file = request.files.get("outputs_file")
        if not model_type or cases_file is None or outputs_file is None:
            return jsonify({
                "status": "invalid",
                "error_code": "MISSING_FIELD",
                "message": "model_type, cases_file and outputs_file are required",
                "dataset_version": None,
                "errors": [],
            }), 400

        result = persist_upload(
            storage,
            runtime_root / "uploads",
            model_type,
            cases_file,
            outputs_file,
        )
        status_code = 200 if result["status"] == "valid" else 422
        return jsonify(result), status_code

    @app.post("/api/tasks")
    def create_evaluation_task():
        payload = request.get_json(silent=True) or {}
        try:
            result = create_task(
                storage,
                runtime_root,
                str(payload.get("upload_id", "")),
                str(payload.get("runner_mode", "")),
            )
        except LookupError:
            return jsonify({
                "status": "invalid",
                "error_code": "UPLOAD_NOT_FOUND",
                "message": "upload_id does not exist",
                "errors": [],
            }), 404
        except ValueError as exc:
            return jsonify({
                "status": "invalid",
                "error_code": "INVALID_REQUEST",
                "message": str(exc),
                "errors": [],
            }), 400
        return jsonify({"task_id": result["task_id"], "status": result["status"]}), 202

    @app.get("/api/tasks/<task_id>")
    def task_status(task_id):
        result = get_task(storage, task_id)
        if result is None:
            return jsonify({
                "status": "invalid",
                "error_code": "TASK_NOT_FOUND",
                "message": "task_id does not exist",
                "errors": [],
            }), 404
        return jsonify(result)

    @app.post("/api/tasks/<task_id>/retry")
    def retry_evaluation_task(task_id):
        try:
            result = retry_task(storage, runtime_root, task_id)
        except LookupError:
            return jsonify({
                "status": "invalid",
                "error_code": "TASK_NOT_FOUND",
                "message": "task_id does not exist",
                "errors": [],
            }), 404
        return jsonify({"task_id": result["task_id"], "status": result["status"]}), 202

    @app.get("/api/tasks/<task_id>/report")
    def task_report(task_id):
        result = get_task(storage, task_id)
        if result is None:
            return jsonify({"error_code": "TASK_NOT_FOUND", "message": "task_id does not exist"}), 404
        if not result.get("report_path"):
            return jsonify({"error_code": "REPORT_NOT_READY", "message": "report is not ready"}), 404
        return Response(Path(result["report_path"]).read_text(encoding="utf-8"), mimetype="text/html")

    @app.get("/api/tasks/<task_id>/results.csv")
    def task_results_csv(task_id):
        result = get_task(storage, task_id)
        if result is None:
            return jsonify({"error_code": "TASK_NOT_FOUND", "message": "task_id does not exist"}), 404
        if not result.get("csv_path"):
            return jsonify({"error_code": "REPORT_NOT_READY", "message": "report is not ready"}), 404
        return send_file(result["csv_path"], mimetype="text/csv", as_attachment=True)

    return app
