# LLM/RAG/Agent 工具配置说明

本目录只覆盖 v0.1 的 LLM/RAG/Agent 评估配置。v0.1 目标是验证评估系统结构，不调用付费 API，不接真实生产数据。

## 文件说明

- `../cases/llm_cases.jsonl`: 20 条合成 LLM 样本。结构化抽取 8 条，知识/RAG 问答 4 条，业务流程 4 条，安全/边界 4 条。
- `promptfoo.yaml`: Promptfoo 最小配置，用 `echo` provider 做离线 smoke test。后续可以把真实 provider 通过环境变量接入。
- `deepeval_pytest_example.py`: pytest 风格示例，从 JSONL 读取样本。DeepEval 未安装时，DeepEval 专项测试会跳过。
- `ragas_eval_example.py`: Ragas 最小结构示例，从 RAG 样本生成 dataset。Ragas 未安装时会打印安装提示并退出。

## 什么时候用哪个工具

- Promptfoo: 用于 prompt 或 provider 横向对比，适合先跑小矩阵，确认 prompts、providers、tests、assertions 能串起来。
- DeepEval: 用于把关键 LLM/Agent 行为写成可回归测试，适合接入 CI 或本地 pytest。
- Ragas: 用于 RAG 专项评估，关注 faithfulness、answer relevancy、context recall 等指标。

## v0.1 离线运行

Promptfoo smoke test:

```bash
cd /Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/configs
promptfoo eval -c promptfoo.yaml
```

DeepEval/pytest 示例:

```bash
cd /Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/configs
python3 -m pytest deepeval_pytest_example.py
```

如果没有安装 DeepEval，只有 DeepEval 专项测试会跳过；基础 JSONL 读取和 mock 输出检查仍可运行。

Ragas 示例:

```bash
cd /Users/mac/Documents/研究报告/outputs/model_eval_framework/eval_mvp/configs
python3 ragas_eval_example.py
```

如果没有安装 Ragas 或 datasets，脚本会提示:

```text
pip install ragas datasets
```

## 环境变量

v0.1 默认不需要任何真实 API key。

后续接真实 provider 时建议只使用环境变量，不要写入配置文件:

```bash
export OPENAI_API_KEY="..."
```

`promptfoo.yaml` 中已经保留了 OpenAI provider 的注释示例。需要真实模型时再取消注释。

## v0.1 不做的事

- 不调用付费 API。
- 不接真实生产数据。
- 不在样本中保存真实客户信息、真实订单、真实证件或真实支付数据。
- 不把工具分数当成上线结论，只验证评估链路和样本结构可用。
