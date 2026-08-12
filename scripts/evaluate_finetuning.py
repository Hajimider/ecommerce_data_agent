import argparse
import gc
import json
import sys
import time
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import SQL_SYSTEM, extract_plan
from config import get_settings
from database import execute_select
from llm_client import LLMClient, LocalLLMClient
from scripts.distillation_data import build_user_prompt, read_jsonl


def parse_args():
    parser = argparse.ArgumentParser(description="比较本地基础模型、LoRA 学生和可选 API 教师")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--adapter-path", default="outputs/student_lora")
    parser.add_argument("--test-path", default="data/evaluation/test.jsonl")
    parser.add_argument("--report-path", default="outputs/evaluation.json")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--include-api", action="store_true")
    return parser.parse_args()


def question_requires_order(question):
    return any(keyword in question for keyword in ("排序", "排列", "升序", "降序", "从高到低", "从低到高", "排在前面"))


def result_signature(columns, rows, ordered):
    normalized_rows = [[str(value) for value in row] for row in rows]
    if not ordered:
        normalized_rows.sort(key=lambda row: json.dumps(row, ensure_ascii=False))
    return json.dumps({"column_count": len(columns), "rows": normalized_rows}, ensure_ascii=False, sort_keys=True)


def evaluate_client(name, client, settings, records):
    extracted = executable = correct = first_success = retries = calls = 0
    errors = []
    started = time.perf_counter()
    for record in records:
        expected_columns, expected_rows, _ = execute_select(settings, record["sql"])
        predicted_sql = raw = ""
        first_error = ""
        was_extracted = False
        was_executable = False
        try:
            calls += 1
            raw = client.chat(SQL_SYSTEM, build_user_prompt(record["question"]))
            predicted_sql = extract_plan(raw)
            was_extracted = True
            columns, rows, _ = execute_select(settings, predicted_sql)
            was_executable = True
            first_success += 1
        except Exception as exc:
            first_error = str(exc)
            retries += 1
            try:
                calls += 1
                repair_prompt = f"{build_user_prompt(record['question'])}\n上一条 SQL 执行失败：{first_error}\n请仅修复 SQL。"
                raw = client.chat(SQL_SYSTEM, repair_prompt)
                predicted_sql = extract_plan(raw)
                was_extracted = True
                columns, rows, _ = execute_select(settings, predicted_sql)
                was_executable = True
            except Exception as retry_error:
                extracted += int(was_extracted)
                executable += int(was_executable)
                if len(errors) < 5:
                    errors.append({"id": record["id"], "问题": record["question"], "阶段": "生成或执行失败", "首次错误": first_error, "重试错误": str(retry_error), "原始输出": raw})
                continue

        extracted += int(was_extracted)
        executable += int(was_executable)

        ordered = question_requires_order(record["question"])
        if result_signature(columns, rows, ordered) == result_signature(expected_columns, expected_rows, ordered):
            correct += 1
        elif len(errors) < 5:
            errors.append({"id": record["id"], "问题": record["question"], "阶段": "结果不一致", "期望SQL": record["sql"], "预测SQL": predicted_sql})

    elapsed = time.perf_counter() - started
    count = len(records)
    return {
        "模型": name,
        "样本数": count,
        "JSON_SQL提取率": round(extracted / count, 4),
        "SQL可执行率": round(executable / count, 4),
        "执行结果正确率": round(correct / count, 4),
        "Agent首次成功率": round(first_success / count, 4),
        "Agent重试率": round(retries / count, 4),
        "模型调用次数": calls,
        "总耗时秒": round(elapsed, 2),
        "平均每题秒": round(elapsed / count, 2),
        "典型错误": errors,
    }


def release_client(client):
    client.model = None
    client.tokenizer = None
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def main():
    args = parse_args()
    model_path = Path(args.model_path)
    adapter_path = Path(args.adapter_path)
    if not model_path.is_dir():
        raise SystemExit("错误：--model-path 不是有效的本地模型目录")
    if not adapter_path.is_dir():
        raise SystemExit("错误：--adapter-path 不是有效的 LoRA 目录，请先完成训练")
    records = read_jsonl(args.test_path)
    if args.max_samples:
        records = records[: args.max_samples]
    if not records:
        raise SystemExit("错误：评测集为空")

    settings = get_settings()
    local_common = replace(settings, mode="local", local_model_path=str(model_path), local_threads=max(1, args.threads), local_max_new_tokens=args.max_new_tokens)
    report = {"说明": "严格微调对比看基础模型与 LoRA；API 教师仅作能力上限参考。", "测试集": args.test_path, "结果": {}}

    base_client = LocalLLMClient(replace(local_common, local_adapter_path=""))
    report["结果"]["本地基础模型"] = evaluate_client("本地基础模型", base_client, settings, records)
    release_client(base_client)

    lora_client = LocalLLMClient(replace(local_common, local_adapter_path=str(adapter_path)))
    report["结果"]["LoRA学生模型"] = evaluate_client("LoRA学生模型", lora_client, settings, records)
    release_client(lora_client)

    if args.include_api:
        api_client = LLMClient(settings)
        report["结果"]["API教师模型"] = evaluate_client("API教师模型", api_client, settings, records)

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"评测报告已保存到：{report_path}")


if __name__ == "__main__":
    main()
