import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.distillation_data import HUMAN_TEST_CASES, build_record, write_jsonl


def parse_args():
    parser = argparse.ArgumentParser(description="生成人工编写、与蒸馏训练隔离的评测集")
    parser.add_argument("--output-path", default="data/evaluation/test.jsonl")
    return parser.parse_args()


def main():
    args = parse_args()
    records = [build_record(case_id, question, sql, "human_test") for case_id, question, sql in HUMAN_TEST_CASES]
    write_jsonl(args.output_path, records)
    print(f"人工测试集已写入：{args.output_path}（{len(records)} 条）")


if __name__ == "__main__":
    main()
