# Model Eval Platform v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the local single-user model evaluation platform v0.1 defined in `specs/model-eval-platform-v0.1-spec.md`, then verify the full STT/TTS/LLM browser and smoke-test workflow before any Git commit.

**Architecture:** Keep the existing Flask route → `mvp` modules → SQLite/filesystem architecture. Implement only the v0.1 platform gaps: robust API errors, safe non-ASCII upload handling, real browser task creation/status/report flow, task detail page, recent task list, and acceptance coverage. Do not add real model adapters, auth, cloud deployment, ranking, or multi-user features.

**Tech Stack:** Python 3.9, Flask, sqlite3, unittest, vanilla HTML/CSS/JavaScript, existing local scorers.

---

## Current baseline

Authoritative repo:

```text
/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp
```

Current branch:

```text
feat/spec-mvp
```

Known current-state gaps from read-only probes:

- `mvp/upload_service.py` derives extension from `secure_filename(...)`, so `案例.jsonl` is rejected.
- `mvp/app.py` catches `HTTPException` as generic `Exception`, so API 404/405 become 500.
- `static/app.js` enables `#create-task` after upload success but does not call `POST /api/tasks`.
- `/tasks/<task_id>` route and task detail page are missing.
- homepage has no recent task list.
- browser flow cannot complete `upload → create task → task status → report → CSV`.
- current tests do not cover these gaps.

Runtime constraint for this Codex session:

- The original repo is read-only from this session.
- Implement in a writable copy under `/Users/mac/Documents/vibe coding`.
- Generate a patch for the original repo.
- Only commit after the patch is applied to the original repo and all acceptance checks pass there.

## File responsibility map

- `mvp/app.py`: Flask app factory, API/page routes, HTTP error envelopes.
- `mvp/upload_service.py`: upload filename handling, extension validation, staging/final persistence.
- `mvp/pipeline.py`: task lifecycle, summaries, retry, recent task summaries.
- `mvp/reporting.py`: escaped HTML and CSV report generation.
- `templates/index.html`: upload form, create-task controls, recent task shell.
- `templates/task.html`: task detail page.
- `static/app.js`: browser flow for upload, create task, polling, task links.
- `static/app.css`: minimal page styling.
- `tests/test_api.py`: upload/API/frontend page behavior.
- `tests/test_pipeline.py`: task lifecycle, retry, reports.
- `tests/test_reporting.py`: HTML escaping and report retry behavior.
- `scripts/smoke_test.py`: port-level STT/TTS/LLM smoke test.
- `README.md`: final user-facing run/verify instructions.
- `docs/specs/model-eval-platform-v0.1-spec.md`: confirmed platform Spec.

---

### Task 1: Create writable implementation copy and sync Spec/plan

**Files:**

- Create: `/Users/mac/Documents/vibe coding/eval_mvp_platform_work/`
- Create: `docs/specs/model-eval-platform-v0.1-spec.md`
- Create: `docs/superpowers/plans/2026-07-10-model-eval-platform-v0.1.md`

- [ ] **Step 1: Create copy without runtime artifacts**

Run:

```bash
cd "/Users/mac/Documents/vibe coding"
mkdir -p eval_mvp_platform_work
cp -R "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/mvp" eval_mvp_platform_work/
cp -R "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/scorers" eval_mvp_platform_work/
cp -R "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/static" eval_mvp_platform_work/
cp -R "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/templates" eval_mvp_platform_work/
cp -R "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/tests" eval_mvp_platform_work/
cp -R "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/scripts" eval_mvp_platform_work/
cp -R "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/sample_packages" eval_mvp_platform_work/
cp "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/app.py" eval_mvp_platform_work/
cp "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/requirements.txt" eval_mvp_platform_work/
cp "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/README.md" eval_mvp_platform_work/
cp "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.gitignore" eval_mvp_platform_work/
mkdir -p eval_mvp_platform_work/docs/specs eval_mvp_platform_work/docs/superpowers/plans
cp "/Users/mac/Documents/vibe coding/specs/model-eval-platform-v0.1-spec.md" eval_mvp_platform_work/docs/specs/
cp "/Users/mac/Documents/vibe coding/docs/superpowers/plans/2026-07-10-model-eval-platform-v0.1.md" eval_mvp_platform_work/docs/superpowers/plans/
```

Expected:

```text
eval_mvp_platform_work contains app.py, mvp/, tests/, static/, templates/, docs/
```

- [ ] **Step 2: Verify baseline tests in copy**

Run:

```bash
cd "/Users/mac/Documents/vibe coding/eval_mvp_platform_work"
"/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" -m unittest discover -s tests -v
```

Expected:

```text
Ran 27 tests
OK
```

---

### Task 2: Add failing acceptance tests for upload and API error gaps

**Files:**

- Modify: `tests/test_api.py`
- Modify: `mvp/app.py`
- Modify: `mvp/upload_service.py`

- [ ] **Step 1: Add tests for non-ASCII `.jsonl` and `.csv` filenames**

Add to `UploadApiTests` in `tests/test_api.py` after `test_valid_upload_persists_sanitized_originals_and_frozen_dataset`:

```python
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
```

- [ ] **Step 2: Add tests for API 404/405 envelopes**

Add to `UploadApiTests` after `test_unexpected_upload_failure_uses_safe_internal_error_envelope`:

```python
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
```

- [ ] **Step 3: Run new tests and confirm RED**

Run:

```bash
"/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" -m unittest \
  tests.test_api.UploadApiTests.test_valid_upload_accepts_non_ascii_jsonl_filenames \
  tests.test_api.UploadApiTests.test_valid_upload_accepts_non_ascii_csv_filenames \
  tests.test_api.UploadApiTests.test_unknown_api_route_returns_http_error_envelope \
  tests.test_api.UploadApiTests.test_wrong_api_method_returns_http_error_envelope \
  -v
```

Expected:

```text
FAILED (failures=4)
```

- [ ] **Step 4: Fix filename handling minimally**

In `mvp/upload_service.py`, replace `_submitted_basename` and add `_display_filename`:

```python
def _submitted_basename(filename: str) -> str:
    return Path(filename.replace("\\", "/")).name


def _display_filename(filename: str) -> str:
    safe_name = secure_filename(filename)
    return safe_name or filename or "<unnamed>"
```

Then change extension errors:

```python
"filename": _display_filename(filename),
```

- [ ] **Step 5: Fix HTTPException handling minimally**

In `mvp/app.py`, add:

```python
from werkzeug.exceptions import HTTPException
```

Replace the global exception handler with:

```python
    @app.errorhandler(Exception)
    def error_response(error):
        if isinstance(error, HTTPException):
            error_code = error.name.upper().replace(" ", "_")
            return jsonify({
                "status": "error",
                "error_code": error_code,
                "message": error.description,
                "errors": [],
            }), error.code

        return jsonify({
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred while processing the request",
            "errors": [],
        }), 500
```

- [ ] **Step 6: Run tests and confirm GREEN**

Run the same command from Step 3.

Expected:

```text
Ran 4 tests
OK
```

---

### Task 3: Implement browser task creation and task detail flow

**Files:**

- Modify: `mvp/app.py`
- Modify: `mvp/pipeline.py`
- Modify: `templates/index.html`
- Create: `templates/task.html`
- Modify: `static/app.js`
- Modify: `static/app.css`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add failing API/page tests**

Add to `tests/test_api.py`:

```python
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
        task_id = task_response.get_json()["task_id"]

        response = self.client.get(f"/tasks/{task_id}")

        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn(task_id, html)
        self.assertIn("report", html)
        self.assertIn("results.csv", html)

    def test_missing_task_detail_page_returns_404(self):
        response = self.client.get("/tasks/task_missing")

        self.assertEqual(404, response.status_code)
```

- [ ] **Step 2: Run new tests and confirm RED**

Run:

```bash
"/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" -m unittest \
  tests.test_api.UploadApiTests.test_index_exposes_create_task_controls_and_recent_tasks \
  tests.test_api.UploadApiTests.test_task_detail_page_shows_status_and_report_links \
  tests.test_api.UploadApiTests.test_missing_task_detail_page_returns_404 \
  -v
```

Expected: failures because JS lacks create task flow and `/tasks/<task_id>` route is missing.

- [ ] **Step 3: Add recent task query**

Add to `mvp/pipeline.py`:

```python
def list_recent_tasks(storage: Storage, limit: int = 20) -> list[dict[str, Any]]:
    with storage.connect() as connection:
        connection.row_factory = lambda cursor, row: {
            column[0]: row[index] for index, column in enumerate(cursor.description)
        }
        rows = connection.execute(
            """
            SELECT
                t.task_id, t.model_type, t.status, t.created_at,
                COALESCE(r.status, 'pending') AS report_status
            FROM tasks t
            LEFT JOIN reports r ON r.task_id = t.task_id
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return list(rows)
```

- [ ] **Step 4: Add page routes**

In `mvp/app.py`, import:

```python
from .pipeline import create_task, get_task, list_recent_tasks, retry_task
```

Change index route:

```python
    @app.get("/")
    def index():
        return render_template("index.html", recent_tasks=list_recent_tasks(storage))
```

Add task page route:

```python
    @app.get("/tasks/<task_id>")
    def task_page(task_id):
        result = get_task(storage, task_id)
        if result is None:
            return render_template("task.html", task=None, task_id=task_id), 404
        return render_template("task.html", task=result, task_id=task_id)
```

- [ ] **Step 5: Update homepage template**

Replace `templates/index.html` body content inside `<main>` with:

```html
    <h1>模型评估平台 v0.1</h1>
    <p>上传 cases 与 outputs，校验通过后创建 fixture 评估任务。</p>
    <form id="upload-form">
      <label>模型类型
        <select name="model_type">
          <option value="STT">STT</option>
          <option value="TTS">TTS</option>
          <option value="LLM">LLM</option>
        </select>
      </label>
      <label>Cases 文件
        <input type="file" name="cases_file" accept=".jsonl,.csv" required>
      </label>
      <label>Outputs 文件
        <input type="file" name="outputs_file" accept=".jsonl,.csv" required>
      </label>
      <button type="submit">上传并校验</button>
      <button type="button" id="create-task" disabled>创建任务</button>
    </form>
    <section aria-live="polite">
      <p id="upload-result"></p>
      <p id="task-status"></p>
      <ul id="upload-errors"></ul>
      <ul id="upload-warnings"></ul>
    </section>
    <section>
      <h2>最近任务</h2>
      <ul id="recent-tasks">
        {% for task in recent_tasks %}
          <li>
            <a href="{{ url_for('task_page', task_id=task.task_id) }}">{{ task.task_id }}</a>
            · {{ task.model_type }} · {{ task.status }} · report: {{ task.report_status }}
          </li>
        {% else %}
          <li>暂无任务</li>
        {% endfor %}
      </ul>
    </section>
```

- [ ] **Step 6: Create task detail template**

Create `templates/task.html`:

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>任务 {{ task_id }}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='app.css') }}">
</head>
<body>
  <main>
    <p><a href="{{ url_for('index') }}">返回首页</a></p>
    {% if task %}
      <h1>任务 {{ task.task_id }}</h1>
      <dl>
        <dt>模型类型</dt><dd>{{ task.model_type }}</dd>
        <dt>状态</dt><dd>{{ task.status }}</dd>
        <dt>进度</dt><dd>{{ task.progress }}%</dd>
        <dt>数据集版本</dt><dd>{{ task.dataset_version }}</dd>
        <dt>报告状态</dt><dd>{{ task.report_status }}</dd>
      </dl>
      <h2>计数</h2>
      <ul>
        <li>total: {{ task.counts.total }}</li>
        <li>succeeded: {{ task.counts.succeeded }}</li>
        <li>failed: {{ task.counts.failed }}</li>
        <li>review_required: {{ task.counts.review_required }}</li>
      </ul>
      {% if task.report_status == "ready" %}
        <p><a href="{{ url_for('task_report', task_id=task.task_id) }}">打开 HTML 报告</a></p>
        <p><a href="{{ url_for('task_results_csv', task_id=task.task_id) }}">下载 results.csv</a></p>
      {% else %}
        <p>报告尚未生成。</p>
      {% endif %}
      <button type="button" id="retry-task" data-task-id="{{ task.task_id }}">重试失败样本</button>
    {% else %}
      <h1>任务不存在</h1>
      <p>{{ task_id }} 不存在。</p>
    {% endif %}
  </main>
</body>
</html>
```

- [ ] **Step 7: Update browser JavaScript**

Replace `static/app.js` with:

```javascript
const form = document.querySelector("#upload-form");
const result = document.querySelector("#upload-result");
const taskStatus = document.querySelector("#task-status");
const errors = document.querySelector("#upload-errors");
const warnings = document.querySelector("#upload-warnings");
const createTask = document.querySelector("#create-task");

let currentUploadId = null;

function renderDiagnostics(target, diagnostics) {
  target.replaceChildren();
  diagnostics.forEach((diagnostic) => {
    const item = document.createElement("li");
    item.textContent = [
      diagnostic.filename,
      diagnostic.line ? `第 ${diagnostic.line} 行` : "",
      diagnostic.field,
      diagnostic.reason,
    ].filter(Boolean).join(" · ");
    target.append(item);
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  currentUploadId = null;
  createTask.disabled = true;
  result.textContent = "正在校验…";
  taskStatus.textContent = "";
  errors.replaceChildren();
  warnings.replaceChildren();

  try {
    const response = await fetch("/api/uploads", {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    renderDiagnostics(warnings, payload.warnings || []);
    if (payload.status === "valid") {
      currentUploadId = payload.upload_id;
      result.textContent = `校验通过：${payload.valid_records} 条有效记录`;
      createTask.disabled = false;
      return;
    }
    result.textContent = "校验未通过";
    renderDiagnostics(errors, payload.errors || [{
      filename: "",
      line: 0,
      field: "",
      reason: payload.message || "上传失败",
    }]);
  } catch {
    result.textContent = "上传失败，请确认本地服务正在运行后重试。";
  }
});

createTask.addEventListener("click", async () => {
  if (!currentUploadId) {
    return;
  }
  createTask.disabled = true;
  taskStatus.textContent = "正在创建任务…";
  try {
    const response = await fetch("/api/tasks", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({upload_id: currentUploadId, runner_mode: "fixture"}),
    });
    const payload = await response.json();
    if (!response.ok) {
      taskStatus.textContent = payload.message || "创建任务失败";
      createTask.disabled = false;
      return;
    }
    const link = document.createElement("a");
    link.href = `/tasks/${payload.task_id}`;
    link.textContent = `任务 ${payload.task_id} 已创建，点击查看`;
    taskStatus.replaceChildren(link);
  } catch {
    taskStatus.textContent = "创建任务失败，请确认本地服务正在运行后重试。";
    createTask.disabled = false;
  }
});
```

- [ ] **Step 8: Run tests and confirm GREEN**

Run command from Step 2.

Expected:

```text
Ran 3 tests
OK
```

---

### Task 4: Add report safety and CSV acceptance coverage

**Files:**

- Create: `tests/test_reporting.py`
- Modify: `mvp/reporting.py` only if tests reveal a gap.

- [ ] **Step 1: Add HTML escaping test**

Create `tests/test_reporting.py`:

```python
import html
import io
import json
import tempfile
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
        return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records).encode("utf-8")

    def test_report_escapes_html_from_case_ids_and_notes(self):
        script_case_id = "<script>alert(1)</script>"
        upload = self.client.post(
            "/api/uploads",
            data={
                "model_type": "TTS",
                "cases_file": (
                    io.BytesIO(self._jsonl([{
                        "case_id": script_case_id,
                        "scenario": "xss",
                        "language": "en",
                        "input_text": "hello Alice",
                        "critical_entities": ["Alice"],
                    }])),
                    "cases.jsonl",
                ),
                "outputs_file": (
                    io.BytesIO(self._jsonl([{
                        "case_id": script_case_id,
                        "roundtrip_text": "hello Bob",
                    }])),
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

        report = self.client.get(f"/api/tasks/{task_id}/report")

        self.assertEqual(200, report.status_code)
        html_text = report.get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", html_text)
        self.assertIn(html.escape(script_case_id), html_text)
```

- [ ] **Step 2: Run test**

Run:

```bash
"/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" -m unittest tests.test_reporting -v
```

Expected:

```text
OK
```

If it fails because report details omit escaped case ids, update `mvp/reporting.py` detail rendering to include escaped `case_id`, `metric`, and `notes` exactly through `html.escape(str(value))`.

---

### Task 5: Extend smoke coverage for page and API acceptance

**Files:**

- Modify: `scripts/smoke_test.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Add page route checks to smoke script**

In `scripts/smoke_test.py`, after `check_report`, add:

```python
def check_task_page(base_url: str, task_id: str) -> None:
    request = urllib.request.Request(base_url.rstrip("/") + f"/tasks/{task_id}")
    with urllib.request.urlopen(request, timeout=10) as response:
        content = response.read().decode("utf-8")
        if response.status != 200 or task_id not in content or "results.csv" not in content:
            raise RuntimeError(f"task page not available for {task_id}")
```

Call it in the model loop:

```python
            check_task_page(args.base_url, task_id)
```

- [ ] **Step 2: Add direct API regression probe test**

Add to `tests/test_api.py`:

```python
    def test_api_acceptance_probe_for_platform_gaps(self):
        upload = self.client.post(
            "/api/uploads",
            data=self.valid_stt_upload("案例.jsonl", "输出.jsonl"),
            content_type="multipart/form-data",
        )
        self.assertEqual(200, upload.status_code)
        self.assertEqual(404, self.client.get("/api/not-found").status_code)
        self.assertEqual(405, self.client.get("/api/uploads").status_code)
```

- [ ] **Step 3: Run API tests**

Run:

```bash
"/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" -m unittest tests.test_api -v
```

Expected:

```text
OK
```

---

### Task 6: Final verification in writable copy

**Files:**

- No code changes unless verification reveals a defect.

- [ ] **Step 1: Run full unit suite**

Run:

```bash
cd "/Users/mac/Documents/vibe coding/eval_mvp_platform_work"
"/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" -m unittest discover -s tests -v
```

Expected:

```text
OK
```

- [ ] **Step 2: Run syntax checks**

Run:

```bash
PYTHONPYCACHEPREFIX=/tmp/eval_mvp_platform_pycache \
  "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" \
  -m compileall mvp tests app.py
node --check static/app.js
"/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" app.py --help
```

Expected:

```text
compileall exits 0
node exits 0
app.py prints --host and --port help
```

- [ ] **Step 3: Run in-process STT/TTS/LLM smoke**

Run:

```bash
"/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/.venv/bin/python" - <<'PY'
import tempfile, time
from pathlib import Path
from mvp.app import create_app

root = Path(tempfile.mkdtemp(prefix="eval_mvp_smoke_"))
project = Path.cwd()
client = create_app({"TESTING": True, "RUNTIME_ROOT": root}).test_client()

for model_type in ("STT", "TTS", "LLM"):
    prefix = model_type.lower()
    with (project / "sample_packages" / f"{prefix}_cases.jsonl").open("rb") as cases_file, (
        project / "sample_packages" / f"{prefix}_outputs.jsonl"
    ).open("rb") as outputs_file:
        upload = client.post(
            "/api/uploads",
            data={
                "model_type": model_type,
                "cases_file": (cases_file, f"{prefix}_cases.jsonl"),
                "outputs_file": (outputs_file, f"{prefix}_outputs.jsonl"),
            },
            content_type="multipart/form-data",
        )
    assert upload.status_code == 200, upload.get_data(as_text=True)
    task = client.post(
        "/api/tasks",
        json={"upload_id": upload.get_json()["upload_id"], "runner_mode": "fixture"},
    )
    assert task.status_code == 202, task.get_data(as_text=True)
    task_id = task.get_json()["task_id"]
    for _ in range(50):
        status = client.get(f"/api/tasks/{task_id}").get_json()
        if status["status"] in {"completed", "partially_completed"} and status["report_status"] == "ready":
            break
        time.sleep(0.05)
    else:
        raise AssertionError(f"{model_type} did not finish: {status}")
    report = client.get(f"/api/tasks/{task_id}/report")
    csv = client.get(f"/api/tasks/{task_id}/results.csv")
    page = client.get(f"/tasks/{task_id}")
    assert report.status_code == 200 and report.get_data(), model_type
    assert csv.status_code == 200 and csv.get_data(), model_type
    assert page.status_code == 200 and task_id in page.get_data(as_text=True), model_type
    print(f"{model_type} task: {status['status']}")

print("In-process smoke test: passed")
PY
```

Expected:

```text
STT task: completed
TTS task: completed
LLM task: completed
In-process smoke test: passed
```

---

### Task 7: Generate original-repo patch and apply outside this sandbox

**Files:**

- Create: `/Users/mac/Documents/vibe coding/eval_mvp_platform_v0.1.patch`

- [ ] **Step 1: Generate patch**

Run:

```bash
cd "/Users/mac/Documents/vibe coding"
python3 - <<'PY'
from pathlib import Path
import difflib

orig = Path("/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp")
work = Path("/Users/mac/Documents/vibe coding/eval_mvp_platform_work")
rels = [
    Path("docs/specs/model-eval-platform-v0.1-spec.md"),
    Path("docs/superpowers/plans/2026-07-10-model-eval-platform-v0.1.md"),
    Path("mvp/app.py"),
    Path("mvp/upload_service.py"),
    Path("mvp/pipeline.py"),
    Path("mvp/reporting.py"),
    Path("templates/index.html"),
    Path("templates/task.html"),
    Path("static/app.js"),
    Path("static/app.css"),
    Path("tests/test_api.py"),
    Path("tests/test_reporting.py"),
    Path("scripts/smoke_test.py"),
    Path("README.md"),
]
chunks = []
for rel in rels:
    before_path = orig / rel
    after_path = work / rel
    before = before_path.read_text(encoding="utf-8").splitlines(keepends=True) if before_path.exists() else []
    after = after_path.read_text(encoding="utf-8").splitlines(keepends=True)
    if before != after:
        chunks.extend(difflib.unified_diff(before, after, fromfile=f"a/{rel}", tofile=f"b/{rel}"))
Path("eval_mvp_platform_v0.1.patch").write_text("".join(chunks), encoding="utf-8")
print("eval_mvp_platform_v0.1.patch")
PY
```

Expected:

```text
eval_mvp_platform_v0.1.patch
```

- [ ] **Step 2: Check patch applies**

Run:

```bash
cd "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp"
git apply --check "/Users/mac/Documents/vibe coding/eval_mvp_platform_v0.1.patch"
```

Expected:

```text
exit code 0
```

- [ ] **Step 3: Apply patch in original repo**

Run from a terminal or a Codex session whose workspace root is the original repo:

```bash
cd "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp"
git apply "/Users/mac/Documents/vibe coding/eval_mvp_platform_v0.1.patch"
```

Expected:

```text
git status --short shows only planned files changed
```

---

### Task 8: Verify original repo, then commit and push

**Files:**

- All modified files from Task 7.

- [ ] **Step 1: Run original repo verification**

Run:

```bash
cd "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp"
./.venv/bin/python -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/eval_mvp_pycache_final ./.venv/bin/python -m compileall mvp tests app.py
node --check static/app.js
./.venv/bin/python app.py --help
git diff --check
```

Expected:

```text
unittest OK
compileall OK
node exits 0
app.py help includes --host and --port
git diff --check exits 0
```

- [ ] **Step 2: Run port-level smoke test**

Terminal 1:

```bash
cd "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp"
./.venv/bin/python app.py --host 127.0.0.1 --port 8766
```

Terminal 2:

```bash
cd "/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp"
./.venv/bin/python scripts/smoke_test.py --base-url http://127.0.0.1:8766
```

Expected:

```text
Smoke test: passed
```

- [ ] **Step 3: Commit only after all verification passes**

Run:

```bash
git status --short
git add docs/specs/model-eval-platform-v0.1-spec.md \
  docs/superpowers/plans/2026-07-10-model-eval-platform-v0.1.md \
  mvp/app.py mvp/upload_service.py mvp/pipeline.py mvp/reporting.py \
  templates/index.html templates/task.html static/app.js static/app.css \
  tests/test_api.py tests/test_reporting.py scripts/smoke_test.py README.md
git commit -m "feat: complete local evaluation platform v0.1"
git push origin feat/spec-mvp
```

Expected:

```text
commit succeeds
push succeeds
```
