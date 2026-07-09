#!/usr/bin/env python3
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path


REPORTS_DIR = Path(__file__).resolve().parent
FRAMEWORK_DIR = REPORTS_DIR.parents[1]
INPUT_CSV = REPORTS_DIR / "sample_eval_summary.csv"
OUTPUT_JS = FRAMEWORK_DIR / "dashboard_data.js"

REQUIRED_FIELDS = {
    "model_type",
    "case_id",
    "tool",
    "metric",
    "score",
    "severity",
    "business_usability",
    "human_review_required",
    "notes",
}

PRIMARY_QUESTIONS = {
    "STT": "能否在真实音频条件下保留意图、关键实体和否定/状态关系？",
    "TTS": "能否忠实、清楚、自然地读出高风险业务文本？",
    "LLM": "能否在给定上下文和边界内稳定完成任务？",
}

RISK_ORDER = {"Critical": 3, "Major": 2, "Minor": 1}
RISK_LABEL = {"Critical": "High", "Major": "Medium", "Minor": "Low"}
USABILITY_FAILS = {"blocked", "review_required"}


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_FIELDS.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(sorted(missing))}")
        return list(reader)


def parse_bool(value):
    return str(value).strip().lower() == "true"


def parse_score(value):
    try:
        return float(value)
    except ValueError:
        return 0.0


def build_status(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["model_type"]].append(row)

    status = []
    for model_type in sorted(grouped):
        model_rows = grouped[model_type]
        total = len(model_rows)
        human_review_count = sum(parse_bool(row["human_review_required"]) for row in model_rows)
        failed_count = sum(row["business_usability"] in USABILITY_FAILS for row in model_rows)
        worst = max(model_rows, key=lambda row: RISK_ORDER.get(row["severity"], 0))["severity"]
        metrics = sorted({row["metric"] for row in model_rows})
        gaps = []
        if failed_count:
            gaps.append(f"{failed_count} 个待处理风险")
        if human_review_count:
            gaps.append(f"{human_review_count} 个需人工复核")
        if not gaps:
            gaps.append("暂无阻塞项")

        status.append({
            "type": model_type,
            "readiness": round(100 * (total - failed_count) / total) if total else 0,
            "automation": round(100 * (total - human_review_count) / total) if total else 0,
            "risk": RISK_LABEL.get(worst, "Low"),
            "primaryQuestion": PRIMARY_QUESTIONS.get(model_type, "该模型类型是否达到业务可用阈值？"),
            "metrics": metrics,
            "mvpCases": total,
            "gaps": gaps,
        })
    return status


def build_failure_modes(rows):
    failures = []
    for row in rows:
        if row["severity"] == "Minor" and row["business_usability"] == "usable":
            continue
        failures.append({
            "type": row["model_type"],
            "severity": row["severity"],
            "name": f"{row['tool']} · {row['metric']}",
            "example": row["notes"],
            "score": parse_score(row["score"]),
            "caseId": row["case_id"],
            "source": row.get("source", ""),
        })
    return sorted(
        failures,
        key=lambda item: (-RISK_ORDER.get(item["severity"], 0), item["type"], item["caseId"]),
    )


def build_data(rows):
    sources = sorted({row.get("source", row["tool"]).strip() for row in rows})
    return {
        "updatedAt": date.today().isoformat(),
        "status": build_status(rows),
        "failureModes": build_failure_modes(rows),
        "phases": [
            {
                "phase": "v0.1",
                "title": "统一报告契约",
                "items": ["sample_eval_summary.csv", "sample_tool_results.jsonl", "source 标识"],
            },
            {
                "phase": "v0.1",
                "title": "样例结果接入",
                "items": ["STT/TTS/LLM", "失败模式", "人工复核标记"],
            },
            {
                "phase": "下一步",
                "title": "工具输出转换",
                "items": sources,
            },
        ],
    }


def main():
    rows = read_rows(INPUT_CSV)
    data = build_data(rows)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    OUTPUT_JS.write_text(f"window.EVAL_DASHBOARD_DATA = {payload};\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_JS}")


if __name__ == "__main__":
    main()
