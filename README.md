# Model Eval MVP v0.1

## v0.1 目标

v0.1 的目标是验证评估系统本身是否跑得通，不评估真实模型优劣。

本版只证明这条链路可执行：

```text
upload cases/outputs -> validate -> create task -> score -> generate report
```

如果没有 API key，先使用模拟输出完成流程验证。只有在接入真实模型、真实或脱敏样本、固定运行配置后，结果才可用于候选模型比较。

## 目录说明

```text
eval_mvp/
  README.md
  cases/              # STT / TTS / LLM case 样本
  configs/            # Promptfoo、DeepEval、Ragas 等工具配置示例
  scorers/            # 本地评分脚本
  runs/               # 每次运行的原始模型输出或模拟输出
  reports/            # 汇总报告、操作手册、路线图
  sample_packages/    # 可直接用于冒烟测试的上传样例
  scripts/            # 本地验收脚本
```

职责边界：

- `cases/` 只放评估输入和期望，不放模型输出。
- `runs/` 放一次执行产生的输出，包含真实模型输出或模拟输出。
- `scorers/` 放可复跑的评分脚本。
- `reports/` 放汇总结果、发布材料和人工复核记录。
- 看板只消费聚合后的报告数据，不直接承担评分逻辑。

## MVP 运行方式

本地依赖已安装在 `eval_mvp/.venv`。启动本地 Web MVP：

```text
./.venv/bin/python app.py --host 127.0.0.1 --port 8766
```

执行自动冒烟测试：

```text
./.venv/bin/python scripts/smoke_test.py --base-url http://127.0.0.1:8766
```

开发验证：

```text
./.venv/bin/python -m unittest discover -s tests -v
```

## 无 API key 模式

无 API key 时，v0.1 使用模拟输出。

适用目的：

- 验证 case 格式是否可读。
- 验证 scorer 是否能生成结果。
- 验证报告字段是否完整。
- 验证看板是否能展示结果。
- 验证失败样本和人工复核项是否能沉淀。

限制：

- 不能证明任何真实模型更好或更差。
- 不能生成模型选型建议。
- 不能作为上线阈值依据。
- 不能对外发布模型排名。

## 真实模型模式

真实模型模式需要先准备：

- 候选模型清单和版本号。
- API key 或本地推理入口。
- 固定的 case 集合。
- 固定的 prompt、voice_id、语言和场景配置。
- 数据来源说明，包含是否脱敏、是否含真实业务数据。
- 人工评分人员和复核规则。

真实模型模式适用目的：

- 小样本候选模型比较。
- 失败样本归因。
- 工具评分与人工评分的一致性检查。
- 为 v0.2 或试点阶段提供选型证据。
