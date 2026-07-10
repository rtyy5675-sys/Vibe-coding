# 模型评估平台 v0.1 Spec

版本：v0.1
日期：2026-07-10
状态：Implemented and verified
目标落点：`/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/docs/specs/model-eval-platform-v0.1-spec.md`

## 1. 背景与目标

本 Spec 用于把现有模型评估 MVP 收束成一个可操作的本地 Web 平台。平台 v0.1 的目标不是评价真实模型优劣，而是证明以下流程可由一个本地系统稳定跑通：

```text
上传评估材料
→ 自动校验
→ 冻结数据集版本
→ 创建评估任务
→ fixture/mock 批量执行
→ STT/TTS/LLM 自动评分
→ 失败样本归档与重试
→ 自动生成 HTML 报告和 CSV 明细
→ 在页面查看任务与报告
```

v0.1 完成后，用户应能在本机通过浏览器和一条 smoke test 命令验证 STT、TTS、LLM 三类评估流程。

## 2. 用户与使用场景

### 2.1 目标用户

- 内部模型测试人员。
- 研究人员或产品/策略人员，用于验证评估流程是否可复用。
- 单用户、本地运行，不涉及账号、权限和组织协作。

### 2.2 核心使用场景

1. 用户打开本地页面。
2. 选择模型类型：STT、TTS 或 LLM。
3. 上传 cases 文件和 outputs 文件。
4. 页面显示校验结果、错误、警告。
5. 校验通过后，用户创建 fixture 任务。
6. 系统执行任务、保存逐条结果。
7. 用户查看任务进度、失败样本和待复核数。
8. 任务完成后，用户打开 HTML 报告或下载 CSV 明细。
9. 如存在失败样本，用户触发 retry，仅重试失败或未完成项。

## 3. 范围

### 3.1 MUST

- 本地 Flask Web 平台。
- SQLite 持久化。
- JSONL 和 CSV 上传。
- STT、TTS、LLM 三类评估材料。
- fixture/mock runner，不调用付费模型。
- 严格材料校验与稳定错误码。
- 冻结数据集版本 `dataset_version`。
- 任务创建、状态查询、进度统计。
- 单条样本持久化执行状态。
- STT WER/CER/实体评分。
- TTS 回转文本实体评分。
- LLM 本地规则断言评分。
- 失败或未完成样本 retry。
- HTML 报告和 CSV 明细。
- 页面完成上传、创建任务、查看任务、打开报告。
- 自动化 unittest 与端到端 smoke test。

### 3.2 SHOULD

- 首页展示最近 20 个任务。
- 上传 checksum 去重或至少返回 checksum。
- partially_completed 也生成报告。
- 报告中保留 fixture 模式免责声明。
- API 错误返回用户可读 message。

### 3.3 MUST NOT

- 不调用付费模型。
- 不存储 API key。
- 不接入生产数据。
- 不输出模型排名或选型结论。
- 不实现多用户、权限、审计系统。
- 不引入分布式任务队列。
- 不实现云部署。

## 4. 平台架构

```text
Browser UI
  │
  ▼
Flask Routes
  ├── upload API
  ├── task API
  ├── retry API
  ├── report API
  └── page routes
       │
       ▼
mvp modules
  ├── ingestion.py       # 文件解析、字段校验、canonical 生成输入
  ├── upload_service.py  # 上传落盘、checksum、dataset_version
  ├── storage.py         # SQLite schema 与连接
  ├── pipeline.py        # 任务创建、执行、retry、状态聚合
  └── reporting.py       # HTML/CSV 报告生成
       │
       ▼
scorers
  ├── score_stt_jiwer.py
  ├── score_tts_roundtrip.py
  ├── score_entities.py
  └── score_llm_rules.py
```

### 4.1 边界原则

- Flask route 层只做请求解析、响应封装和页面路由。
- ingestion 不访问数据库。
- storage 不理解业务评分。
- pipeline 负责任务生命周期，不直接拼 HTML。
- reporting 只读取持久化结果并生成报告，不重新执行评分。
- scorers 保持纯函数或近似纯函数，便于单独测试。

## 5. 数据与文件约定

### 5.1 运行目录

```text
eval_mvp/
  app.py
  mvp/
  scorers/
  templates/
  static/
  sample_packages/
  scripts/
  tests/
  data/
  uploads/
  runs/
  reports/generated/
```

### 5.2 上传材料

每次上传包含：

- `model_type`: `STT`、`TTS`、`LLM`
- `cases_file`: `.jsonl` 或 `.csv`
- `outputs_file`: `.jsonl` 或 `.csv`

公共规则：

- 文件必须是 UTF-8。
- JSONL 每个非空行必须是 JSON object。
- CSV 第一行必须是唯一非空字段名。
- CSV 中 array/object 字段必须使用合法 JSON 字符串。
- `case_id` 必须存在、非空、在 cases 内唯一。
- outputs 通过 `case_id` 匹配 cases。
- cases 缺失 output 允许上传，但执行时该 case 必须 failed。
- outputs 中未知 `case_id` 进入 warning，不参与任务。
- 校验失败不得生成 `dataset_version`。

### 5.3 文件名安全

- 扩展名判断必须基于路径剥离后的原始提交文件名，而不是 `secure_filename` 之后的结果。
- 服务器端落盘文件名固定为 `cases.<ext>` 与 `outputs.<ext>`。
- 非 ASCII 文件名，例如 `案例.jsonl`、`输出.csv`，只要扩展名合法，必须可上传。
- 错误展示中的文件名必须净化，不能形成路径穿越。

## 6. API 规范

### 6.1 上传

```http
POST /api/uploads
Content-Type: multipart/form-data
```

请求字段：

- `model_type`
- `cases_file`
- `outputs_file`

成功响应状态码：`200`

```json
{
  "status": "valid",
  "upload_id": "upl_xxx",
  "model_type": "STT",
  "dataset_version": "STT-<checksum>-<timestamp>",
  "checksum": "<combined_checksum>",
  "checksums": {
    "cases": "<sha256>",
    "outputs": "<sha256>"
  },
  "total_records": 10,
  "valid_records": 10,
  "invalid_records": 0,
  "errors": [],
  "warnings": []
}
```

校验失败响应状态码：`422`

```json
{
  "status": "invalid",
  "error_code": "INVALID_JSON",
  "message": "JSON parse error",
  "dataset_version": null,
  "errors": [
    {
      "error_code": "INVALID_JSON",
      "filename": "cases.jsonl",
      "line": 3,
      "field": "",
      "reason": "..."
    }
  ],
  "warnings": []
}
```

### 6.2 创建任务

```http
POST /api/tasks
Content-Type: application/json
```

```json
{
  "upload_id": "upl_xxx",
  "runner_mode": "fixture"
}
```

成功响应状态码：`202`

```json
{
  "task_id": "task_xxx",
  "status": "queued"
}
```

v0.1 仅支持 `runner_mode=fixture`。

### 6.3 查询任务

```http
GET /api/tasks/<task_id>
```

```json
{
  "task_id": "task_xxx",
  "model_type": "STT",
  "status": "completed",
  "progress": 100,
  "counts": {
    "total": 10,
    "pending": 0,
    "running": 0,
    "succeeded": 10,
    "failed": 0,
    "review_required": 1
  },
  "report_status": "ready",
  "report_path": ".../report.html",
  "csv_path": ".../results.csv"
}
```

### 6.4 重试任务

```http
POST /api/tasks/<task_id>/retry
```

成功响应状态码：`202`

规则：

- 只处理 failed、pending、retryable 状态样本。
- succeeded 样本不得再次评分。
- retry 后必须更新 `attempt_count`。

### 6.5 报告访问

```http
GET /api/tasks/<task_id>/report
GET /api/tasks/<task_id>/results.csv
```

报告未生成时返回 `REPORT_NOT_READY`。

## 7. 页面规范

### 7.1 首页 `/`

首页必须包含：

- 模型类型选择。
- cases 文件上传控件。
- outputs 文件上传控件。
- 上传/校验按钮。
- 创建任务按钮。
- 校验结果区域。
- 错误列表。
- 警告列表。
- 最近任务列表。

交互规则：

- 上传前，“创建任务”必须禁用。
- 校验失败后，“创建任务”保持禁用。
- 校验通过后，页面必须保存当前 `upload_id` 并启用“创建任务”。
- “创建任务”按钮启用时必须已经绑定 `POST /api/tasks`，不能出现可点击但无效的入口。
- 创建任务成功后，页面必须展示任务链接或直接进入任务详情页。

### 7.2 任务详情页 `/tasks/<task_id>`

任务详情页必须包含：

- task_id。
- 模型类型。
- 状态。
- 进度。
- total、succeeded、failed、review_required。
- 报告状态。
- HTML 报告入口。
- CSV 下载入口。
- retry 按钮或 retry 操作入口。

### 7.3 HTML 安全

- 页面和报告中展示用户输入时必须 HTML 转义。
- 包含 `<script>` 的样本不得在报告中执行。

## 8. 数据库结构

SQLite 必须包含以下表：

- `uploads`
- `datasets`
- `tasks`
- `task_items`
- `results`
- `reports`

### 8.1 uploads

- upload_id
- model_type
- cases_path
- outputs_path
- checksum
- status
- validation_json
- created_at

### 8.2 datasets

- dataset_version
- upload_id
- canonical_cases_path
- canonical_outputs_path
- sample_count
- created_at

### 8.3 tasks

- task_id
- dataset_version
- model_type
- runner_mode
- status
- scorer_version
- created_at
- started_at
- completed_at

### 8.4 task_items

- task_id
- case_id
- status
- attempt_count
- error_message
- started_at
- completed_at

主键必须为 `(task_id, case_id)`。

### 8.5 results

- result_id
- task_id
- case_id
- metric
- score
- severity
- business_usability
- human_review_required
- scorer
- scorer_version
- dataset_version
- run_status
- notes

### 8.6 reports

- report_id
- task_id
- status
- html_path
- csv_path
- template_version
- generated_at

## 9. 任务执行与评分

### 9.1 状态

任务状态：

- queued
- running
- completed
- partially_completed
- failed
- cancelled

task_item 状态：

- pending
- running
- succeeded
- failed

progress 计算：

```text
(succeeded + failed) / total * 100
```

### 9.2 STT

输入：

- `reference_text`
- `critical_entities`

输出：

- `transcript`

允许 aliases：

- `prediction`
- `predicted_text`
- `output_text`

结果必须包含：

- WER
- CER
- entity_pass
- entity_score
- missing_entities

### 9.3 TTS

输入：

- `input_text`
- `critical_entities`

输出：

- `roundtrip_text`

结果必须包含：

- entity_pass
- entity_score
- missing_entities
- human_review_required

### 9.4 LLM

必须支持断言：

- `valid_json`
- `contains_required_fields`
- `exact_match_entities`
- `contains_required_facts`
- `does_not_contain_forbidden_steps`
- `no_hallucinated_entities`
- `does_not_contain_false_guarantee`
- `contains_limitation`

无法识别的 assertion 必须记录为 `unsupported`，不得静默判定通过。

## 10. 报告规范

### 10.1 HTML 报告

HTML 报告必须包含：

- task_id。
- 生成时间。
- 模型类型。
- dataset_version。
- 总样本数。
- 成功数。
- 失败数。
- 待复核数。
- 自动评分覆盖率。
- scenario 汇总。
- metric 汇总。
- severity 汇总。
- Critical/Major 明细。
- 失败样本及失败原因。
- scorer 和 scorer_version。
- fixture 模式免责声明。

### 10.2 CSV 明细

CSV 每个 case 至少一行。多 metric 可多行。

每行至少包含：

- task_id
- case_id
- model_type
- metric
- score
- severity
- business_usability
- human_review_required
- scorer
- scorer_version
- dataset_version
- run_status
- notes

## 11. 错误处理

### 11.1 稳定错误码

必须支持：

- INVALID_FILE_TYPE
- INVALID_ENCODING
- INVALID_JSON
- INVALID_CSV
- MISSING_FIELD
- INVALID_FIELD_TYPE
- DUPLICATE_CASE_ID
- DUPLICATE_OUTPUT_CASE_ID
- INVALID_MODEL_TYPE
- UPLOAD_NOT_FOUND
- UPLOAD_NOT_VALID
- TASK_NOT_FOUND
- INVALID_STATE_TRANSITION
- REPORT_NOT_READY
- INTERNAL_ERROR

### 11.2 HTTP 错误

- `/api/...` 未知路由必须返回 HTTP 404，不得变成 500。
- 方法不允许必须返回 HTTP 405，不得变成 500。
- API HTTP 错误必须返回 JSON envelope。
- 未预期异常必须返回 `INTERNAL_ERROR`，不得泄漏异常文本。

## 12. 验收测试

### AT-001 STT 完整链路

上传 STT 示例包，创建任务，最终状态为 completed，生成 HTML 和 CSV，结果包含 WER、CER、entity_score。

### AT-002 TTS 完整链路

上传 TTS 示例包，创建任务，最终状态为 completed 或 partially_completed，生成 HTML 和 CSV，结果包含 entity_score 与 human_review_required。

### AT-003 LLM 完整链路

上传 LLM 示例包，创建任务，最终状态为 completed，生成 HTML 和 CSV，结果包含本地断言结果。

### AT-004 非法材料

上传非法 JSON、坏 CSV、缺字段、重复 `case_id`，系统返回稳定错误码，且不得创建 dataset_version。

### AT-005 缺失输出

缺失 output 的 case 在上传阶段产生 warning，任务执行后该 case 为 failed，其他样本继续执行。

### AT-006 失败重试

retry 只处理 failed 或未完成样本；succeeded 样本 attempt_count 不变。

### AT-007 API 错误 envelope

未知 `/api/...` 路由返回 404 JSON envelope；错误 HTTP 方法返回 405 JSON envelope；内部异常返回 500 `INTERNAL_ERROR` 且不泄漏异常文本。

### AT-008 非 ASCII 文件名

`案例.jsonl`、`输出.jsonl`、`案例.csv`、`输出.csv` 必须可上传；服务端保存固定文件名。

### AT-009 HTML 安全

样本中包含 HTML 或 script 字符串时，报告必须转义显示，不得执行。

### AT-010 页面端到端

浏览器页面必须能完成：

```text
上传 → 校验通过 → 创建任务 → 查看任务进度 → 打开报告 → 下载 CSV
```

### AT-011 冒烟脚本

`scripts/smoke_test.py --base-url http://127.0.0.1:8766` 必须完成 STT、TTS、LLM 三类流程，退出码为 0，并输出：

```text
Smoke test: passed
```

## 13. 完成条件

以下检查全部通过后，v0.1 才算完成：

```bash
./.venv/bin/python -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/eval_mvp_pycache ./.venv/bin/python -m compileall mvp tests app.py
node --check static/app.js
./.venv/bin/python app.py --help
```

端口级 smoke test：

```bash
./.venv/bin/python app.py --host 127.0.0.1 --port 8766
./.venv/bin/python scripts/smoke_test.py --base-url http://127.0.0.1:8766
```

Git 提交前必须满足：

- 工作树只包含本 Spec 对应修改。
- 无运行产物被纳入提交。
- `.gitignore` 覆盖 `data/`、`uploads/`、`runs/`、`reports/generated/`、`.venv/`、`__pycache__/`。
- 所有 AT-001 到 AT-011 有测试或 smoke evidence 覆盖。

## 14. v0.2 延后事项

- 真实模型 adapter。
- API key 管理。
- 成本统计。
- 多模型横向对比。
- 模型排名或选型建议。
- 多用户权限。
- 云部署。
- 人工听评工作台。
- PDF/PPT 导出。
