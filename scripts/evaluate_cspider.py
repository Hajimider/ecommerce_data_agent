import argparse
import gc
import json
import re
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_settings
from llm_client import LocalLLMClient
from scripts.distillation_data import read_jsonl


FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|PRAGMA)\b", re.I)


def parse_args():
    parser = argparse.ArgumentParser(description="比较基础模型与 LoRA 在 CSpider dev 子集上的轻量执行结果")
    parser.add_argument("--model-path", required=False, default="")
    parser.add_argument("--adapter-path", default="outputs/student_lora")
    parser.add_argument("--test-path", default="data/evaluation/cspider_dev.jsonl")
    parser.add_argument("--source-dir", default="data/public/cspider/raw")
    parser.add_argument("--database-dir", default="", help="默认使用 source-dir/database")
    parser.add_argument("--report-path", default="outputs/evaluation_cspider.json")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def normalize_public_sql(sql):
    if not isinstance(sql, str):
        raise ValueError("SQL 必须是文本")
    sql = sql.strip()
    if not re.match(r"^(SELECT|WITH)\b", sql, flags=re.I):
        raise ValueError("公开评测只允许 SELECT 或 WITH 查询")
    if FORBIDDEN_SQL.search(sql) or "--" in sql or "/*" in sql:
        raise ValueError("SQL 包含不允许的操作或注释")
    body = sql.rstrip(";").strip()
    if ";" in body:
        raise ValueError("一次只能执行一条 SQL")
    return body + ";"


def extract_public_sql(text):
    cleaned = text.replace("```json", "").replace("```sql", "").replace("```", "").strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            data, _ = decoder.raw_decode(cleaned[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "sql" in data:
            return normalize_public_sql(data["sql"])
    raise ValueError("模型没有返回合法的 JSON SQL")


def execute_sqlite(database_path, sql):
    uri = Path(database_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        cursor = connection.execute(normalize_public_sql(sql))
        return cursor.fetchall()


def normalized_value(value):
    if isinstance(value, float):
        return round(value, 8)
    return value


def result_signature(rows, ordered):
    normalized = [[normalized_value(value) for value in row] for row in rows]
    if not ordered:
        normalized.sort(key=lambda row: json.dumps(row, ensure_ascii=False, default=str))
    return json.dumps(normalized, ensure_ascii=False, default=str)


def evaluate_client(name, client, records, database_dir):
    extracted = executable = correct = calls = 0
    errors = []
    started = time.perf_counter()
    for record in records:
        database_path = database_dir / record["db_id"] / f"{record['db_id']}.sqlite"
        try:
            expected_rows = execute_sqlite(database_path, record["sql"])
        except Exception as exc:
            raise ValueError(f"标准 SQL 无法执行（{record['id']}）：{exc}") from exc

        raw = predicted_sql = ""
        try:
            calls += 1
            raw = client.chat(record["messages"][0]["content"], record["messages"][1]["content"])
            predicted_sql = extract_public_sql(raw)
            extracted += 1
            predicted_rows = execute_sqlite(database_path, predicted_sql)
            executable += 1
            ordered = "ORDER BY" in record["sql"].upper()
            if result_signature(predicted_rows, ordered) == result_signature(expected_rows, ordered):
                correct += 1
            elif len(errors) < 10:
                errors.append({
                    "id": record["id"], "db_id": record["db_id"], "问题": record["question"],
                    "阶段": "执行结果不一致", "期望SQL": record["sql"], "预测SQL": predicted_sql,
                })
        except Exception as exc:
            if len(errors) < 10:
                errors.append({
                    "id": record["id"], "db_id": record["db_id"], "问题": record["question"],
                    "阶段": "生成或执行失败", "错误": str(exc), "原始输出": raw,
                })

    elapsed = time.perf_counter() - started
    count = len(records)
    return {
        "模型": name,
        "样本数": count,
        "JSON_SQL提取率": round(extracted / count, 4),
        "SQL可执行率": round(executable / count, 4),
        "轻量执行结果正确率": round(correct / count, 4),
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


def self_test():
    assert normalize_public_sql("SELECT 1") == "SELECT 1;"
    assert extract_public_sql('说明 {"sql":"SELECT 1;"} 尾部') == "SELECT 1;"
    try:
        normalize_public_sql("DELETE FROM users")
        raise AssertionError("危险 SQL 未被拒绝")
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as temporary_dir:
        database_path = Path(temporary_dir) / "test.sqlite"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute("CREATE TABLE t (id INTEGER)")
            connection.executemany("INSERT INTO t VALUES (?)", [(2,), (1,)])
            connection.commit()
        assert execute_sqlite(database_path, "SELECT id FROM t ORDER BY id") == [(1,), (2,)]
    print("CSpider 公开评测自检通过。")


def main():
    args = parse_args()
    if args.self_test:
        self_test()
        return
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
        raise SystemExit("错误：公开评测集为空")
    source_dir = Path(args.source_dir)
    database_dir = Path(args.database_dir) if args.database_dir else source_dir / "database"

    settings = get_settings()
    local_common = replace(
        settings, mode="local", local_model_path=str(model_path),
        local_threads=max(1, args.threads), local_max_new_tokens=args.max_new_tokens,
    )
    report = {
        "说明": "CSpider dev 固定子集轻量执行评测，不等同于 CSpider 官方全量评测，也不与电商 MySQL 指标混算。",
        "数据集": "CSpider",
        "测试集": args.test_path,
        "结果": {},
    }

    try:
        base_client = LocalLLMClient(replace(local_common, local_adapter_path=""))
        report["结果"]["本地基础模型"] = evaluate_client("本地基础模型", base_client, records, database_dir)
        release_client(base_client)

        lora_client = LocalLLMClient(replace(local_common, local_adapter_path=str(adapter_path)))
        report["结果"]["LoRA学生模型"] = evaluate_client("LoRA学生模型", lora_client, records, database_dir)
        release_client(lora_client)
    except (FileNotFoundError, ValueError, sqlite3.Error) as exc:
        raise SystemExit(f"错误：{exc}") from exc

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"公开评测报告已保存到：{report_path}")


if __name__ == "__main__":
    main()
