"""IDE 一键对比基础模型与 LoRA 在同一道测试题上的表现。"""

import sys
import time
from dataclasses import replace
from pathlib import Path

from agent import SQL_SYSTEM, extract_plan
from config import get_settings
from database import execute_select, format_sql, format_table
from llm_client import LocalLLMClient
from scripts.distillation_data import build_user_prompt, read_jsonl
from scripts.evaluate_finetuning import question_requires_order, release_client, result_signature


# 留空时读取 .env 中的 LOCAL_MODEL_PATH。
MODEL_PATH = ""
ADAPTER_PATH = "outputs/student_lora_epoch2"
TEST_PATH = "data/evaluation/test.jsonl"

# 从独立测试集中选一题，避免使用训练题做演示。
TEST_CASE_ID = "test_completed_month_count"
THREADS = 8
MAX_NEW_TOKENS = 256
ROOT = Path(__file__).resolve().parent


def project_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def select_record(records, record_id):
    for record in records:
        if record["id"] == record_id:
            return record
    available = "、".join(record["id"] for record in records)
    raise ValueError(f"找不到测试题 {record_id!r}，可选值：{available}")


def run_model(name, client, settings, record, expected_columns, expected_rows):
    started = time.perf_counter()
    sql = ""
    try:
        raw = client.chat(SQL_SYSTEM, build_user_prompt(record["question"]))
        sql = extract_plan(raw)
        columns, rows, _ = execute_select(settings, sql)
        ordered = question_requires_order(record["question"])
        correct = result_signature(columns, rows, ordered) == result_signature(expected_columns, expected_rows, ordered)
        return {"name": name, "sql": sql, "columns": columns, "rows": rows, "executable": True, "correct": correct, "error": "", "seconds": time.perf_counter() - started}
    except Exception as exc:
        return {"name": name, "sql": sql, "columns": [], "rows": [], "executable": False, "correct": False, "error": str(exc), "seconds": time.perf_counter() - started}
    finally:
        release_client(client)


def print_model_result(result):
    print(f"\n===== {result['name']} =====")
    if result["sql"]:
        print("SQL：")
        print(format_sql(result["sql"]))
    if result["executable"]:
        print("\n执行结果：")
        print(format_table(result["columns"], result["rows"]))
    else:
        print(f"生成或执行失败：{result['error']}")
    print(f"结果正确：{'是' if result['correct'] else '否'}")
    print(f"耗时：{result['seconds']:.2f} 秒")


def self_test():
    record = select_record(read_jsonl(project_path(TEST_PATH)), TEST_CASE_ID)
    assert record["id"] == TEST_CASE_ID
    assert record["sql"].upper().startswith("SELECT")
    print(f"对比入口自检通过：已找到独立测试题 {record['id']}。")


def main():
    if "--self-test" in sys.argv:
        self_test()
        return

    settings = get_settings()
    configured_model_path = MODEL_PATH or settings.local_model_path
    if not configured_model_path:
        raise SystemExit("请填写 MODEL_PATH，或在 .env 中配置 LOCAL_MODEL_PATH。")
    if not ADAPTER_PATH:
        raise SystemExit("请填写已经训练完成的 ADAPTER_PATH。")
    model_path = project_path(configured_model_path)
    adapter_path = project_path(ADAPTER_PATH)
    if not model_path.is_dir():
        raise SystemExit("请填写 MODEL_PATH，或在 .env 中配置有效的 LOCAL_MODEL_PATH。")
    if not adapter_path.is_dir():
        raise SystemExit("ADAPTER_PATH 不是有效的 LoRA 目录，请填写已经训练完成的适配器路径。")

    record = select_record(read_jsonl(project_path(TEST_PATH)), TEST_CASE_ID)
    expected_columns, expected_rows, _ = execute_select(settings, record["sql"])
    common = replace(
        settings,
        mode="local",
        local_model_path=str(model_path),
        local_threads=max(1, THREADS),
        local_max_new_tokens=MAX_NEW_TOKENS,
    )

    print("===== 对比问题 =====")
    print(record["question"])
    print("\n===== 标准 SQL =====")
    print(format_sql(record["sql"]))
    print("\n===== 标准执行结果 =====")
    print(format_table(expected_columns, expected_rows))

    base = run_model(
        "本地基础模型",
        LocalLLMClient(replace(common, local_adapter_path="")),
        settings,
        record,
        expected_columns,
        expected_rows,
    )
    lora = run_model(
        "LoRA 微调模型",
        LocalLLMClient(replace(common, local_adapter_path=str(adapter_path))),
        settings,
        record,
        expected_columns,
        expected_rows,
    )
    print_model_result(base)
    print_model_result(lora)

    print("\n===== 对比摘要 =====")
    print(
        format_table(
            ["模型", "SQL可执行", "结果正确", "耗时（秒）"],
            [
                [base["name"], "是" if base["executable"] else "否", "是" if base["correct"] else "否", f"{base['seconds']:.2f}"],
                [lora["name"], "是" if lora["executable"] else "否", "是" if lora["correct"] else "否", f"{lora['seconds']:.2f}"],
            ],
        )
    )


if __name__ == "__main__":
    main()
