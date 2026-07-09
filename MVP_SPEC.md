# 模型自动化评估 MVP 执行 Spec

版本：v0.1  
日期：2026-07-09  
状态：Ready for implementation

## 1. 目标

实现一个本地 Web MVP，使用户能够：

1. 上传 STT、TTS 或 LLM 的评估材料。
2. 自动校验材料并生成冻结数据集。
3. 创建评估任务并查看执行进度。
4. 批量处理 fixture/mock 模型输出。
5. 自动执行对应评分器。
6. 查看异常和失败样本。
7. 自动查看 HTML 报告并下载 CSV 明细。

## 2. 用户与使用场景

### 目标用户

内部模型测试或研究人员，单用户、本地使用。

### 核心场景

```text
用户选择模型类型
→ 上传 cases 和 outputs
→ 系统校验材料
→ 用户创建任务
→ 系统后台执行和评分
→ 用户查看进度
→ 系统生成报告
→ 用户查看 HTML 并下载 CSV
```

## 3. 范围

### MUST

- JSONL 和 CSV 材料上传。
- STT、TTS、LLM 三类任务。
- fixture/mock 输出模式。
- 文件校验和 dataset_version。
- SQLite 持久化。
- 任务状态、进度和失败重试。
- STT WER/CER/实体评分。
- TTS 回转实体评分。
- LLM 本地规则评分。
- HTML 报告和 CSV 明细。
- unittest 和 API 冒烟测试。

### SHOULD

- 上传文件 checksum 去重。
- 任务取消。
- partially_completed 报告。
- 历史任务列表。
- 报告中的成本字段。

### MUST NOT

- 不调用付费模型。
- 不接入生产数据。
- 不存储 API key。
- 不输出模型排名。
- 不实现多用户和权限系统。
- 不引入分布式任务队列。

## 4. 材料契约

### 4.1 公共规则

- 文件编码必须为 UTF-8。
- JSONL 每个非空行必须是 JSON object。
- CSV 第一行必须是字段名。
- CSV 中的 array 或 object 字段必须使用合法 JSON 字符串编码；包括 `critical_entities`、`risk_tags`、`must_not_fail`、`expected`、`assertions` 和 `context`。
- `case_id` 必须存在、非空且在单个 cases 文件内唯一。
- outputs 文件通过 `case_id` 与 cases 文件关联。
- 未匹配 output 的 case 允许上传，但执行时必须标记为 failed。
- outputs 中不存在于 cases 的 case_id 必须进入校验警告，不参与任务。
- 校验失败时不得生成 dataset_version。

### 4.2 STT cases

必填字段：

| 字段 | 类型 |
|---|---|
| case_id | string |
| scenario | string |
| language | string |
| reference_text | string |
| critical_entities | array |

可选字段：

- `audio_ref`
- `risk_tags`
- `must_not_fail`

STT outputs 必须包含：

| 字段 | 类型 |
|---|---|
| case_id | string |
| transcript | string |

允许使用 `prediction`、`predicted_text` 或 `output_text` 代替 `transcript`。

### 4.3 TTS cases

必填字段：

| 字段 | 类型 |
|---|---|
| case_id | string |
| scenario | string |
| language | string |
| input_text | string |
| critical_entities | array |

可选字段：

- `voice_id`
- `risk_tags`
- `human_review_required`

TTS outputs 必须包含：

| 字段 | 类型 |
|---|---|
| case_id | string |
| roundtrip_text | string |

### 4.4 LLM cases

必填字段：

| 字段 | 类型 |
|---|---|
| case_id | string |
| task_type | string |
| input | string |
| expected | object |
| assertions | array |

可选字段：

- `context`
- `risk_tags`

LLM outputs 必须包含：

| 字段 | 类型 |
|---|---|
| case_id | string |
| output | string 或 object |

## 5. 功能需求

### FR-001 应用启动

- MUST 提供 `app.py`。
- MUST 支持 `--host` 和 `--port` 参数。
- MUST 默认监听 `127.0.0.1:8766`。
- MUST 在启动时创建缺失的 data、uploads、runs 和 generated reports 目录。

### FR-002 数据库初始化

- MUST 使用 SQLite 标准库。
- MUST 自动创建 uploads、datasets、tasks、task_items、results、reports 表。
- MUST 使用外键或应用层检查保证 task、dataset 和 result 关联有效。
- MUST 不把原始大文本或二进制音频直接存入 SQLite；数据库只保存路径和元数据。

### FR-003 文件上传

- MUST 提供 `POST /api/uploads`。
- MUST 接收 `model_type`、cases 文件和 outputs 文件。
- MUST 只接受 `.jsonl` 和 `.csv`。
- MUST 返回 `upload_id`、文件 checksum 和校验状态。
- MUST 将文件保存到 `uploads/<upload_id>/`。

### FR-004 自动校验

- MUST 按第 4 节契约校验文件。
- MUST 返回总记录数、有效记录数、无效记录数、错误和警告。
- MUST 为错误提供文件名、行号、字段和原因。
- MUST 拒绝格式损坏、缺少必填字段或 case_id 重复的材料。
- MUST 对 outputs 缺失情况给出警告。

### FR-005 数据集冻结

- MUST 在校验通过后生成 dataset_version。
- dataset_version MUST 由模型类型、文件 checksum 和生成时间共同确定。
- MUST 保存清洗后的 canonical cases 和 outputs 文件。
- MUST 保留原始文件与 canonical 文件的关联。

### FR-006 上传页面

- MUST 在 `/` 提供模型类型选择和 cases/outputs 上传控件。
- MUST 显示上传和校验结果。
- MUST 在校验通过前禁用“创建任务”。
- MUST 显示错误清单，不要求用户查看服务日志。

### FR-007 任务创建

- MUST 提供 `POST /api/tasks`。
- 请求必须包含 `upload_id` 和 `runner_mode=fixture`。
- MUST 生成唯一 task_id。
- MUST 为每个有效 case 创建 task_item。
- MUST 保存 dataset_version、model_type、scorer_version 和创建时间。

### FR-008 任务状态

允许状态：

```text
queued
running
reviewing
completed
partially_completed
failed
cancelled
```

允许转换：

```text
queued → running
queued → cancelled
running → reviewing
running → partially_completed
running → failed
running → cancelled
reviewing → completed
reviewing → partially_completed
partially_completed → running
failed → queued
```

其他状态转换 MUST 被拒绝。

### FR-009 任务进度

- MUST 提供 `GET /api/tasks/<task_id>`。
- MUST 返回 total、pending、running、succeeded、failed 和 review_required 数量。
- MUST 返回 0-100 的 progress。
- progress MUST 使用终态 task_item 数 / total 计算。

### FR-010 批量执行

- MUST 使用后台工作线程，不阻塞 HTTP 请求。
- MUST 将 task_item 状态持久化。
- MUST 单条处理并立即保存结果。
- 单条失败 MUST NOT 中止其他 task_item。
- 应用重启后，遗留 running task_item MUST 变为 retryable failed。
- fixture runner MUST 根据 case_id 读取 canonical outputs。

### FR-011 STT 评分

- MUST 复用 `score_stt_jiwer.py` 和 `score_entities.py`。
- MUST 输出 WER、CER、entity_pass、entity_score 和 missing_entities。
- 缺失 transcript MUST 标记 task_item failed。
- entity_pass=false 且涉及 critical_entities 时 MUST 标记 human_review_required=true。

### FR-012 TTS 评分

- MUST 复用 `score_tts_roundtrip.py`。
- MUST 输出 entity_pass、entity_score 和 missing_entities。
- 缺失 roundtrip_text MUST 标记 task_item failed。
- case 中 human_review_required=true 时结果必须保留该标记。

### FR-013 LLM 评分

MVP MUST 支持以下本地断言：

- `valid_json`
- `contains_required_fields`
- `exact_match_entities`
- `contains_required_facts`
- `does_not_contain_forbidden_steps`
- `no_hallucinated_entities`
- `does_not_contain_false_guarantee`
- `contains_limitation`

无法识别的 assertion MUST 记录为 unsupported，不得静默判定通过。

### FR-014 统一结果

每条结果 MUST 包含：

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

### FR-015 失败重试

- MUST 提供 `POST /api/tasks/<task_id>/retry`。
- MUST 只重试 failed 或未完成 task_item。
- MUST NOT 重跑 succeeded task_item。
- MUST 保存 attempt_count。

### FR-016 报告生成

- completed 和 partially_completed 任务 MUST 自动生成报告。
- MUST 生成 `reports/generated/<task_id>/report.html`。
- MUST 生成 `reports/generated/<task_id>/results.csv`。
- 报告失败 MUST 只重试聚合和文件生成，不得重跑评分。

### FR-017 HTML 报告内容

报告 MUST 包含：

- task_id 和生成时间。
- 模型类型和数据集版本。
- 总样本数、成功数、失败数、待复核数。
- 自动评分覆盖率。
- 按 scenario、metric 和 severity 的汇总。
- Critical 和 Major 明细。
- 失败样本及失败原因。
- scorer 和 scorer_version。
- fixture 模式免责声明。

### FR-018 CSV 明细

CSV MUST 每个 case 至少一行，并包含 FR-014 字段。一个 case 有多个 metric 时允许多行。

### FR-019 任务详情页面

- MUST 提供 `/tasks/<task_id>`。
- MUST 显示任务状态和进度。
- MUST 显示失败数和待复核数。
- MUST 在报告生成后提供 HTML 报告和 CSV 明细入口。
- SHOULD 提供失败任务重试按钮。

### FR-020 历史任务

- 首页 SHOULD 展示最近 20 个任务。
- MUST 显示 task_id、模型类型、状态、创建时间和报告状态。

## 6. API 规范

### 6.1 上传

```http
POST /api/uploads
Content-Type: multipart/form-data
```

字段：

- `model_type`: `STT`、`TTS` 或 `LLM`
- `cases_file`: JSONL 或 CSV
- `outputs_file`: JSONL 或 CSV

成功响应：

```json
{
  "upload_id": "upl_20260709_ab12cd34",
  "status": "valid",
  "dataset_version": "ds_stt_ab12cd34",
  "total_records": 10,
  "valid_records": 10,
  "invalid_records": 0,
  "errors": [],
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
  "upload_id": "upl_20260709_ab12cd34",
  "runner_mode": "fixture"
}
```

成功响应状态码 MUST 为 202：

```json
{
  "task_id": "task_20260709_ef56gh78",
  "status": "queued"
}
```

### 6.3 查询任务

```http
GET /api/tasks/task_20260709_ef56gh78
```

```json
{
  "task_id": "task_20260709_ef56gh78",
  "model_type": "STT",
  "status": "running",
  "progress": 60,
  "counts": {
    "total": 10,
    "pending": 4,
    "running": 0,
    "succeeded": 6,
    "failed": 0,
    "review_required": 1
  },
  "report_status": "pending"
}
```

### 6.4 重试

```http
POST /api/tasks/task_20260709_ef56gh78/retry
```

成功响应状态码 MUST 为 202。

## 7. 数据库最小结构

### uploads

- upload_id
- model_type
- cases_path
- outputs_path
- checksum
- status
- validation_json
- created_at

### datasets

- dataset_version
- upload_id
- canonical_cases_path
- canonical_outputs_path
- sample_count
- created_at

### tasks

- task_id
- dataset_version
- model_type
- runner_mode
- status
- scorer_version
- created_at
- started_at
- completed_at

### task_items

- task_id
- case_id
- status
- attempt_count
- error_message
- started_at
- completed_at

主键 MUST 为 `(task_id, case_id)`。

### results

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
- notes

### reports

- report_id
- task_id
- status
- html_path
- csv_path
- template_version
- generated_at

## 8. 非功能需求

### NFR-001 可复现性

所有结果必须关联 dataset_version 和 scorer_version。

### NFR-002 数据安全

- 文件名必须净化，防止目录穿越。
- 上传文件只能写入 upload_id 对应目录。
- 不执行上传文件中的代码。
- 报告输出必须进行 HTML 转义。

### NFR-003 可靠性

- 单条失败不得导致进程退出。
- SQLite 写入使用事务。
- succeeded task_item 不得重复处理。

### NFR-004 性能

- 40 条 fixture 样本应在普通本地机器上 30 秒内完成。
- 任务查询接口在 fixture 规模下应在 500ms 内返回。

### NFR-005 可维护性

- scorer 与 Web 路由分离。
- storage、ingestion、pipeline 和 reporting 不互相读取对方私有状态。
- 不复制现有 JiWER 和实体评分逻辑。

### NFR-006 可观察性

- 服务日志必须包含 task_id 和 case_id。
- 日志不得包含完整敏感输入。
- API 错误必须返回稳定 error_code 和用户可读 message。

## 9. 错误码

| error_code | 场景 |
|---|---|
| INVALID_FILE_TYPE | 文件扩展名不支持 |
| INVALID_ENCODING | 文件不是 UTF-8 |
| INVALID_JSON | JSONL 行解析失败 |
| MISSING_FIELD | 缺少必填字段 |
| DUPLICATE_CASE_ID | case_id 重复 |
| INVALID_MODEL_TYPE | 模型类型不支持 |
| UPLOAD_NOT_VALID | 上传材料未通过校验 |
| TASK_NOT_FOUND | task_id 不存在 |
| INVALID_STATE_TRANSITION | 非法任务状态转换 |
| REPORT_NOT_READY | 报告尚未生成 |
| INTERNAL_ERROR | 未分类内部错误 |

## 10. 自动化验收测试

### AT-001 STT 完整链路

上传 STT 示例 cases/outputs，创建任务，最终状态为 completed，并生成包含 WER、CER 和 entity_score 的 HTML/CSV。

### AT-002 TTS 完整链路

上传 TTS 示例 cases/outputs，创建任务，最终状态为 completed，并生成 entity_score 和 human_review_required。

### AT-003 LLM 完整链路

上传 LLM 示例 cases/outputs，创建任务，最终状态为 completed，并生成支持断言的通过/失败结果。

### AT-004 非法材料

上传包含非法 JSON 和重复 case_id 的文件，系统返回对应错误码，且不能创建任务。

### AT-005 缺失输出

上传缺少一个 case_id 输出的材料，上传可以完成并产生 warning；任务执行后该 case 必须为 failed，其他 case 正常完成，任务为 partially_completed。

### AT-006 失败重试

通过测试钩子模拟一个可重试的临时评分异常，首次运行后任务为 partially_completed。触发 retry 后只重新处理失败 case，已成功 case 的 attempt_count 不变，重试成功后任务转为 completed。

### AT-007 服务重启

任务执行中停止服务并重新启动，遗留 running item 被标记为可重试，不得错误标记为 completed。

### AT-008 报告重试

模拟报告写入失败，评分结果保持不变；恢复路径后仅重新生成报告。

### AT-009 HTML 安全

输入包含 HTML script 字符串，报告必须转义显示，不得执行。

### AT-010 冒烟脚本

`scripts/smoke_test.py` 依次完成 STT、TTS、LLM 上传、执行和报告检查，最终退出码为 0，并输出：

```text
Smoke test: passed
```

## 11. 完成条件

以下命令全部成功后，Spec 视为完成：

```bash
cd /Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp
./.venv/bin/python -m unittest discover -s tests -v
```

启动服务：

```bash
./.venv/bin/python app.py --host 127.0.0.1 --port 8766
```

执行冒烟测试：

```bash
./.venv/bin/python scripts/smoke_test.py \
  --base-url http://127.0.0.1:8766
```

必须满足：

- unittest 无失败。
- STT、TTS、LLM 三个任务均生成报告。
- 非法材料、缺失输出、重试和报告失败测试通过。
- 没有人工复制中间文件或手工修改结果。
- fixture 结果明确标记为非模型质量结论。
