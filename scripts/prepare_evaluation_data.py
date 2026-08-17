import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.distillation_data import HUMAN_TEST_CASES, build_record, read_jsonl, write_jsonl


EXPECTED_TEST_SAMPLES = 24


def parse_args():
    parser = argparse.ArgumentParser(description="生成人工编写、与蒸馏训练隔离的评测集")
    parser.add_argument("--output-path", default="data/evaluation/test.jsonl")
    parser.add_argument("--train-path", default="data/distillation/fixed_train_72.jsonl")
    parser.add_argument("--check-only", action="store_true", help="只校验已有测试集，不改写文件")
    return parser.parse_args()


def validate_records(records, train_path):
    if len(records) != EXPECTED_TEST_SAMPLES:
        raise ValueError(f"测试集必须固定为 {EXPECTED_TEST_SAMPLES} 条，当前为 {len(records)} 条")

    ids = [record["id"] for record in records]
    questions = [record["question"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("测试集存在重复 id")
    if len(questions) != len(set(questions)):
        raise ValueError("测试集存在重复问题")

    train_records = read_jsonl(train_path)
    normalize_question = lambda value: re.sub(r"\s+", "", value).lower()
    normalize_sql = lambda value: re.sub(r"\s+", "", value).lower()
    train_ids = {record.get("id") for record in train_records}
    train_questions = {normalize_question(record["question"]) for record in train_records}
    train_sql = {normalize_sql(record["sql"]) for record in train_records}
    id_overlaps = sorted(set(ids) & train_ids)
    if id_overlaps:
        raise ValueError(f"测试 ID 与训练集重复：{id_overlaps}")
    question_overlaps = sorted({question for question in questions if normalize_question(question) in train_questions})
    if question_overlaps:
        raise ValueError(f"测试问题与训练集重复：{question_overlaps}")
    sql_overlaps = sorted({record["id"] for record in records if normalize_sql(record["sql"]) in train_sql})
    if sql_overlaps:
        raise ValueError(f"测试 SQL 与训练集重复：{sql_overlaps}")


def check_existing(path, expected_records):
    actual_records = read_jsonl(path)
    expected = [(record["id"], record["question"], record["sql"]) for record in expected_records]
    actual = [(record.get("id"), record.get("question"), record.get("sql")) for record in actual_records]
    if actual != expected:
        raise ValueError(f"固定测试集内容与预期不一致：{path}")


def main():
    args = parse_args()
    records = [build_record(case_id, question, sql, "human_test") for case_id, question, sql in HUMAN_TEST_CASES]
    try:
        validate_records(records, args.train_path)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"错误：{exc}") from exc
    if args.check_only:
        try:
            check_existing(args.output_path, records)
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(f"错误：{exc}") from exc
        print(f"固定测试集校验通过：{args.output_path}（{len(records)} 条，未改写文件）")
    else:
        write_jsonl(args.output_path, records)
        print(f"固定测试集已写入：{args.output_path}（{len(records)} 条，与训练集无重复问题）")


if __name__ == "__main__":
    main()
