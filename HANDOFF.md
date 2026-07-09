# 模型自动化评估 MVP 交接文档

日期：2026-07-09

## 1. 项目目标

本项目需要实现一个本地可运行的模型自动化评估 MVP，验证以下完整链路：

```text
上传评估材料
→ 自动校验并生成数据集版本
→ 创建评估任务
→ 批量执行
→ 自动验证评分
→ 异常归档
→ 自动生成 HTML 报告和 CSV 明细
```

覆盖对象为 STT、TTS 和 LLM。首轮目标是证明评估系统能够跑通，不评判真实模型优劣。

## 2. 当前状态

### 已完成

- 自动化评估研究计划及质量、成本和阶段边界。
- MVP 落地执行计划。
- STT、TTS、LLM 示例用例。
- JiWER STT 评分脚本。
- 关键实体检查脚本。
- TTS 回转文本评分脚本。
- Promptfoo、DeepEval、Ragas 配置示例。
- 报告字段契约、报告模板和静态看板。
- 自动化评估思维导图。

### 尚未实现

- 文件上传接口和操作页面。
- 上传材料自动校验及 dataset_version 生成。
- SQLite 状态存储。
- task_id、任务状态和进度管理。
- 后台批量执行和失败重试。
- LLM 本地确定性评分器。
- HTML 报告和 CSV 明细自动生成。
- 全链路冒烟测试。
- 真实模型 adapter。

不得将现有脚本和静态页面描述为已经完成的自动化评估系统。

## 3. 关键文件

工作目录：

```text
/Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp
```

| 文件 | 用途 |
|---|---|
| `MVP_SPEC.md` | MVP 功能、接口、数据和验收规范 |
| `MVP_IMPLEMENTATION_PLAN.md` | 五日实施顺序和文件级任务 |
| `README.md` | 现有 v0.1 说明和 fixture 模式边界 |
| `AGENT_STATE.md` | 早期脚手架的工作状态，仅作历史参考 |
| `cases/stt_cases.jsonl` | STT 示例用例 |
| `cases/tts_cases.jsonl` | TTS 示例用例 |
| `cases/llm_cases.jsonl` | LLM 示例用例 |
| `scorers/score_stt_jiwer.py` | WER、CER 和实体评分 |
| `scorers/score_entities.py` | 通用关键实体检查 |
| `scorers/score_tts_roundtrip.py` | TTS 回转文本评分 |
| `configs/promptfoo.yaml` | Promptfoo 示例配置 |
| `configs/deepeval_pytest_example.py` | DeepEval 示例 |
| `configs/ragas_eval_example.py` | Ragas 示例 |
| `reports/reporting_contract.md` | 现有归一化结果字段 |
| `reports/build_dashboard_data.py` | CSV 到静态看板数据的转换脚本 |

上级方案文件：

```text
/Users/mac/Documents/研究报告/outputs/model_eval_framework/model_automation_evaluation_concrete_draft.md
```

## 4. 已确认的技术决策

| 决策 | 结论 |
|---|---|
| MVP 形态 | 本地单机、单用户 Web 应用 |
| 后端 | Python + Flask |
| 状态存储 | SQLite，直接使用标准库 sqlite3 |
| 前端 | Vanilla HTML/CSS/JavaScript |
| 后台执行 | 单进程、单工作线程；样本级状态持久化 |
| 首轮执行模式 | fixture/mock 输出 |
| 报告 | HTML 汇总 + CSV 样本明细 |
| 自动测试 | Python unittest |
| STT 评分 | 复用 JiWER 与实体评分器 |
| TTS 评分 | 复用回转文本与实体评分器 |
| LLM 评分 | 首轮新增本地确定性规则评分器 |
| 真实模型 | MVP 跑通后通过 adapter 接入 |

## 5. 环境现状

- `eval_mvp/.venv` 已存在。
- `requirements.txt` 当前只包含 `jiwer`。
- Flask 尚未加入依赖，也未安装。
- 当前目录没有完整应用入口、数据库或测试目录。
- 现有报告和看板数据为样例，不是实际任务运行结果。

开始实施前先确认：

```bash
cd /Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp
./.venv/bin/python --version
./.venv/bin/pip show jiwer
```

然后按 Spec 修改 `requirements.txt`，安装 Flask。

## 6. 推荐执行顺序

1. 阅读 `MVP_SPEC.md`，确认所有 MUST 要求。
2. 阅读 `MVP_IMPLEMENTATION_PLAN.md`，按任务一至任务六执行。
3. 先固化输入、输出和状态契约，不先写页面。
4. 建立 SQLite 和 API，再实现上传校验。
5. 接入 STT、TTS、LLM 本地评分路由。
6. 实现任务详情、HTML 报告和 CSV 明细。
7. 完成 unittest 和全链路冒烟测试。
8. 最后才考虑真实模型 adapter。

## 7. 实施约束

- 只修改 `eval_mvp/` 及必要的 `model_eval_framework` 看板数据文件。
- 不重写现有可复用评分器。
- 不将 API key 写入代码、SQLite、日志或报告。
- 不使用生产数据。
- fixture 结果不得用于模型排名。
- 单条样本失败不得中止整个任务。
- 已成功样本在重试时不得重复执行。
- 无效上传不得创建评估任务。
- 报告生成失败不得触发模型重新运行。
- 所有结果必须可追溯到 task_id、case_id 和版本字段。

## 8. 首轮完成定义

只有同时满足以下条件，MVP 才算完成：

1. STT、TTS、LLM 示例材料均可通过页面上传。
2. 非法 JSONL、缺字段和重复 case_id 能返回明确错误。
3. 三类任务均可从 queued 运行到 completed。
4. 页面可查看任务进度、失败数和报告状态。
5. STT、TTS、LLM 均产生样本级自动评分结果。
6. 每个任务自动生成 HTML 报告和 CSV 明细。
7. 一个失败任务可以只重试失败或未完成样本。
8. `python -m unittest discover -s tests -v` 全部通过。
9. `scripts/smoke_test.py` 完成三类任务并输出 `Smoke test: passed`。

## 9. 真实模型接入前置条件

完成本地 fixture MVP 后，真实模型冒烟验证仍需用户提供或确认：

- STT、TTS、LLM 候选模型和版本。
- API 或本地推理入口。
- API 凭证的使用方式。
- 调用量和费用上限。
- 评估语言。
- TTS voice_id。
- 可使用的数据及脱敏规则。

缺少这些信息时，不得自行选择供应商、上传数据或产生付费调用。

## 10. 交接后的第一项工作

第一项工作是实现 `MVP_SPEC.md` 中的 FR-001 至 FR-006：

1. 建立 Flask 应用入口。
2. 建立 SQLite schema。
3. 实现 JSONL/CSV 文件校验。
4. 生成 upload_id 和 dataset_version。
5. 为以上能力补齐 unittest。

在这些能力通过测试前，不开始任务执行页面或报告样式工作。
