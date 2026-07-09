# 模型自动化评估 MVP 落地执行计划

日期：2026-07-09

## 1. MVP 目标

在本地搭建一个可操作、可复跑的最小系统，验证以下链路能够完整执行：

```text
上传评估材料
→ 自动校验并生成数据集版本
→ 创建评估任务
→ 批量处理样本
→ 自动验证评分
→ 异常样本归档
→ 自动生成 HTML 报告和 CSV 明细
```

本阶段验证评估系统能否跑通，不输出真实模型排名，不形成上线结论。

## 2. 实施假设与边界

| 项目 | MVP 约定 |
|---|---|
| 运行环境 | 单机、本地运行、单用户使用 |
| 技术栈 | Python、Flask、SQLite、Vanilla HTML/CSS/JavaScript |
| 数据规模 | 首轮使用现有 STT 10 条、TTS 10 条、LLM 20 条样本 |
| 执行模式 | 首轮使用 fixture/mock 输出；真实模型通过统一 adapter 后续接入 |
| STT 范围 | 评估参考文本与预测转写，不在首轮调用真实 STT 服务 |
| TTS 范围 | 评估输入文本与回转转写，不在首轮执行真实语音合成和听评 |
| LLM 范围 | 首轮执行本地确定性断言；Promptfoo、DeepEval、Ragas 保留为后续 adapter |
| 用户系统 | 不做账号、权限、多租户和组织管理 |
| 部署 | 不做云部署，使用本地 HTTP 服务 |
| 报告格式 | HTML 汇总报告和 CSV 样本明细 |

首轮 fixture 模式用于证明系统链路可用。真实模型模式需要候选模型、API 凭证、调用限额和数据权限，不属于首轮跑通的前置条件。

## 3. 成功标准

| 核心能力 | MVP 验收标准 |
|---|---|
| 上传评估材料 | 可上传 JSONL 或 CSV；自动检查格式、必填字段和重复 case_id；错误可定位到行 |
| 创建评估任务 | 上传成功后可选择 STT、TTS 或 LLM，生成 task_id 和 dataset_version |
| 自动批量执行 | 任务状态按 queued → running → reviewing/completed 流转；失败样本可单独重试 |
| 自动验证评分 | STT 输出 WER/CER/实体结果；TTS 输出回转实体结果；LLM 输出结构和规则断言结果 |
| 自动汇总报告 | 任务完成后自动生成 HTML 汇总和 CSV 明细 |
| 结果追溯 | 每条结果关联 task_id、case_id、模型类型、数据集版本、评分器版本和运行状态 |
| 异常处理 | 无效材料不进入任务；缺失输出计为失败；任务失败不丢失已完成结果 |
| 全链路验收 | 一个脚本可完成上传、创建任务、轮询状态并验证报告文件存在 |

## 4. 技术方案

### 4.1 系统结构

```text
浏览器操作页
    ↓
Flask API
    ├── 材料接入与校验
    ├── 任务状态与批次执行
    ├── STT/TTS/LLM 评分路由
    ├── SQLite 状态存储
    └── HTML/CSV 报告生成
```

### 4.2 目录规划

```text
eval_mvp/
  app.py
  requirements.txt
  mvp/
    __init__.py
    storage.py
    ingestion.py
    pipeline.py
    reporting.py
  scorers/
    score_entities.py
    score_stt_jiwer.py
    score_tts_roundtrip.py
    score_llm_rules.py
  templates/
    index.html
    task.html
    report.html
  static/
    app.css
    app.js
  sample_packages/
    stt_cases.jsonl
    stt_outputs.jsonl
    tts_cases.jsonl
    tts_outputs.jsonl
    llm_cases.jsonl
    llm_outputs.jsonl
  data/
    eval_mvp.sqlite
  uploads/
  runs/
  reports/
    generated/
  scripts/
    smoke_test.py
  tests/
    test_ingestion.py
    test_pipeline.py
    test_reporting.py
    test_api.py
```

现有 `cases/`、`scorers/`、`reports/` 和看板文件继续复用，不重写已经可用的评分逻辑。

### 4.3 MVP 接口

| 方法 | 地址 | 用途 |
|---|---|---|
| GET | `/` | 上传材料和查看任务列表 |
| POST | `/api/uploads` | 上传 cases 文件和 outputs 文件，执行校验 |
| POST | `/api/tasks` | 根据 upload_id、模型类型和运行配置创建任务 |
| GET | `/api/tasks/<task_id>` | 查询状态、进度、失败数和报告状态 |
| POST | `/api/tasks/<task_id>/retry` | 只重试未完成或系统失败样本 |
| GET | `/api/tasks/<task_id>/report` | 查看 HTML 汇总报告 |
| GET | `/api/tasks/<task_id>/results.csv` | 下载样本级结果明细 |

## 5. 分步实施计划

### 任务一：固化输入、输出和状态契约

**涉及文件**

- 修改：`eval_mvp/reports/reporting_contract.md`
- 新增：`eval_mvp/sample_packages/*`
- 新增：`eval_mvp/tests/test_ingestion.py`

**工作内容**

1. 统一 STT、TTS、LLM 的公共字段：`case_id`、`model_type`、`scenario`、`risk_tags`。
2. 定义 fixture 输出文件，所有输出使用 `case_id` 与输入关联。
3. 明确每类样本的必填字段和允许字段。
4. 从现有样本生成三套可直接上传的 cases/outputs 示例包。
5. 增加合法文件、非法 JSON、缺字段和重复 case_id 测试。

**完成标准**

- 三套示例包均能通过校验。
- 非法文件返回明确的行号和错误原因。
- 无效记录不会生成 dataset_version。

### 任务二：搭建本地服务和状态存储

**涉及文件**

- 新增：`eval_mvp/app.py`
- 新增：`eval_mvp/mvp/__init__.py`
- 新增：`eval_mvp/mvp/storage.py`
- 修改：`eval_mvp/requirements.txt`
- 新增：`eval_mvp/tests/test_api.py`

**工作内容**

1. 增加 Flask 依赖和本地启动入口。
2. 使用 SQLite 建立 uploads、datasets、tasks、task_items、reports 表。
3. 实现 task 状态流转和进度统计。
4. 应用启动时将遗留 running 任务标记为可重试状态，避免假完成。
5. 提供上传、任务创建、任务查询和重试接口。

**完成标准**

- 服务启动后 `/` 和任务 API 可访问。
- 重启服务后已有任务和结果仍可查询。
- 非法状态转换被拒绝并返回明确错误。

### 任务三：实现材料上传与自动校验

**涉及文件**

- 新增：`eval_mvp/mvp/ingestion.py`
- 新增：`eval_mvp/templates/index.html`
- 新增：`eval_mvp/static/app.css`
- 新增：`eval_mvp/static/app.js`
- 完善：`eval_mvp/tests/test_ingestion.py`

**工作内容**

1. 支持上传 JSONL 和 CSV cases 文件及对应 outputs 文件。
2. 保存原文件、计算 checksum、避免重复写入。
3. 校验文件编码、JSON/CSV 格式、必填字段、case_id 唯一性和输入输出关联。
4. 返回总记录数、有效数、无效数和错误清单。
5. 校验通过后生成 dataset_version。
6. 页面展示上传结果并允许基于有效数据创建任务。

**完成标准**

- STT、TTS、LLM 示例包均可从页面上传。
- 缺失输出被标记但不会导致服务崩溃。
- 错误材料不能创建任务。

### 任务四：实现批量执行和评分路由

**涉及文件**

- 新增：`eval_mvp/mvp/pipeline.py`
- 新增：`eval_mvp/scorers/score_llm_rules.py`
- 复用：`eval_mvp/scorers/score_stt_jiwer.py`
- 复用：`eval_mvp/scorers/score_tts_roundtrip.py`
- 新增：`eval_mvp/tests/test_pipeline.py`

**工作内容**

1. 使用后台单工作线程执行任务，避免请求阻塞。
2. 将样本拆成 task_items，逐条保存 pending、running、succeeded、failed 状态。
3. STT 路由到 JiWER、CER 和实体检查。
4. TTS 路由到回转文本与实体检查。
5. LLM 实现 valid_json、required_fields、exact_entities、forbidden_content 等本地断言。
6. 评分结果统一转换为 reporting contract。
7. 中断后只执行 pending 或 retryable 项，不重复评分 succeeded 项。

**完成标准**

- 三类任务均能从 queued 运行到 completed。
- 单条失败不阻断其他样本。
- 重试不会重复处理已成功样本。
- 每条结果均保存评分器版本和评分方式。

### 任务五：实现自动报告和明细导出

**涉及文件**

- 新增：`eval_mvp/mvp/reporting.py`
- 新增：`eval_mvp/templates/report.html`
- 新增：`eval_mvp/templates/task.html`
- 新增：`eval_mvp/tests/test_reporting.py`

**工作内容**

1. 聚合总体样本数、成功率、自动评分覆盖率和人工复核数。
2. 按模型类型、scenario、severity 和 metric 分层汇总。
3. 单独列出 Critical、Major、失败和低置信样本。
4. 输出模型、数据集、配置、评分器和报告模板版本。
5. 自动生成 HTML 报告和 CSV 样本明细。
6. 报告生成失败时只重新聚合结果，不重新调用评分流程。

**完成标准**

- completed 和 partially_completed 任务均能生成报告。
- HTML 汇总与 CSV 明细的样本数一致。
- 报告可追溯到 task_id 和 dataset_version。

### 任务六：完成全链路冒烟测试

**涉及文件**

- 新增：`eval_mvp/scripts/smoke_test.py`
- 完善：`eval_mvp/tests/test_api.py`
- 修改：`eval_mvp/README.md`

**工作内容**

1. 启动本地服务。
2. 通过 API 上传三套示例包。
3. 分别创建 STT、TTS、LLM 任务。
4. 轮询任务直到完成。
5. 验证 HTML 报告和 CSV 明细可访问。
6. 构造一个失败样本，验证失败记录和重试。
7. 更新操作说明和已知限制。

**完成标准**

- 单条命令完成三类任务的端到端冒烟测试。
- 自动化测试全部通过。
- 页面可完成上传、创建任务、查看进度和打开报告。

## 6. 验证命令

实施完成后执行：

```bash
cd outputs/model_eval_framework/eval_mvp
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m unittest discover -s tests -v
./.venv/bin/python app.py --host 127.0.0.1 --port 8766
```

服务启动后另开终端执行：

```bash
./.venv/bin/python scripts/smoke_test.py \
  --base-url http://127.0.0.1:8766
```

预期结果：

```text
STT task: completed
TTS task: completed
LLM task: completed
Reports: 3 HTML, 3 CSV
Retry scenario: passed
Smoke test: passed
```

## 7. 五日执行安排

| 时间 | 工作内容 | 当日验收 |
|---|---|---|
| 第 1 日 | 固化数据契约、示例包、SQLite 和服务骨架 | 上传接口和数据库测试通过 |
| 第 2 日 | 材料校验、数据集版本、上传页面 | 三类示例包均可上传并预览 |
| 第 3 日 | 批量任务、STT/TTS/LLM 评分路由、重试 | 三类任务均可完成 |
| 第 4 日 | HTML 报告、CSV 明细、任务详情页 | 报告自动生成且数据一致 |
| 第 5 日 | 全链路测试、异常测试、文档和最终复核 | 冒烟脚本与全部测试通过 |

## 8. 首轮不做

- 不接入生产数据。
- 不保存或展示 API key。
- 不实现多用户、权限和审计系统。
- 不实现分布式任务队列。
- 不实现完整模型供应商管理。
- 不实现在线人工听评平台。
- 不实现 PDF、PPT 或复杂看板导出。
- 不以 fixture/mock 结果形成模型质量结论。

## 9. 真实模型冒烟验证

本地 MVP 全链路通过后，再增加真实模型 adapter。每类模型先接入一个候选服务，各运行 5-10 条脱敏样本，并验证：

1. 调用参数和模型版本可追溯。
2. 超时、限流和服务错误可正确重试。
3. 调用成本进入任务成本汇总。
4. 真实输出可以复用同一评分与报告流程。
5. adapter 失败不会影响 fixture 模式继续运行。

进入该步骤前需确认候选模型、调用入口、API 凭证、费用上限、语言、TTS voice_id 和数据权限。
