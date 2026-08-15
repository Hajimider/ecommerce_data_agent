import argparse
import json
import random
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import normalize_select
from scripts.distillation_data import read_jsonl, write_jsonl


PUBLIC_SQL_SYSTEM = """你是数据分析场景的 SQL 生成器。请严格依据给出的数据库结构回答问题。
只返回一个 JSON 对象，格式为 {\"sql\":\"一条只读 SQL;\"}，不要 Markdown 或其他文字。
不得编造表名或字段名。"""


def parse_args():
    parser = argparse.ArgumentParser(description="将 CSpider 标准格式转换为本项目的 SFT 与评测 JSONL")
    parser.add_argument("--source-dir", default="data/public/cspider/raw")
    parser.add_argument("--database-dir", default="", help="默认使用 source-dir/database")
    parser.add_argument("--domain-path", default="data/distillation/verified_train.jsonl")
    parser.add_argument("--public-train-output", default="data/public/cspider/processed/train.jsonl")
    parser.add_argument("--combined-output", default="data/training/cspider_ecommerce_train.jsonl")
    parser.add_argument("--dev-output", default="data/evaluation/cspider_dev.jsonl")
    parser.add_argument("--manifest-output", default="data/public/cspider/processed/manifest.json")
    parser.add_argument("--public-train-samples", type=int, default=200, help="0 表示使用全部可用训练样本")
    parser.add_argument("--public-dev-samples", type=int, default=50, help="0 表示使用全部可用开发集样本")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--public-only", action="store_true", help="合并快照中不加入电商领域训练集")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def schema_context(table):
    table_names = table["table_names_original"]
    columns_by_table = [[] for _ in table_names]
    column_lookup = {}
    for column_id, (table_id, column_name) in enumerate(table["column_names_original"]):
        if table_id >= 0:
            columns_by_table[table_id].append(column_name)
            column_lookup[column_id] = (table_names[table_id], column_name)

    table_lines = [f"{name}({', '.join(columns_by_table[index])})" for index, name in enumerate(table_names)]
    foreign_keys = []
    for left_id, right_id in table.get("foreign_keys", []):
        if left_id in column_lookup and right_id in column_lookup:
            left_table, left_column = column_lookup[left_id]
            right_table, right_column = column_lookup[right_id]
            foreign_keys.append(f"{left_table}.{left_column} = {right_table}.{right_column}")

    context = "数据库表结构：\n" + "\n".join(table_lines)
    if foreign_keys:
        context += "\n外键关系：\n" + "\n".join(foreign_keys)
    return context


def build_public_record(split, index, item, table):
    question = item.get("question", "").strip()
    sql = normalize_select(item.get("query", ""))
    if not question:
        raise ValueError("问题为空")
    db_id = item["db_id"]
    user_prompt = f"{schema_context(table)}\n\n用户问题：{question}"
    return {
        "id": f"cspider_{split}_{index}",
        "source": f"cspider_{split}",
        "db_id": db_id,
        "question": question,
        "sql": sql,
        "messages": [
            {"role": "system", "content": PUBLIC_SQL_SYSTEM},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": json.dumps({"sql": sql}, ensure_ascii=False, separators=(",", ":"))},
        ],
    }


def convert_split(items, tables, split):
    records = []
    skipped = 0
    seen = set()
    for index, item in enumerate(items):
        try:
            db_id = item["db_id"]
            record = build_public_record(split, index, item, tables[db_id])
            key = (db_id, record["question"])
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            records.append(record)
        except (KeyError, TypeError, ValueError):
            skipped += 1
    return records, skipped


def sample_records(records, count, seed):
    if count <= 0 or count >= len(records):
        return records
    indexes = sorted(random.Random(seed).sample(range(len(records)), count))
    return [records[index] for index in indexes]


def prepare(args):
    source_dir = Path(args.source_dir)
    train_candidates = [source_dir / "train.json", source_dir / "train_spider.json"]
    train_path = next((path for path in train_candidates if path.is_file()), train_candidates[0])
    dev_path = source_dir / "dev.json"
    tables_path = source_dir / "tables.json"
    required = [train_path, dev_path, tables_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "缺少 CSpider 原始文件：" + "、".join(missing)
            + "。请将标准 Spider 格式的 train.json、dev.json、tables.json 放入 source-dir。"
        )

    database_dir = Path(args.database_dir) if args.database_dir else source_dir / "database"
    tables = {item["db_id"]: item for item in load_json(tables_path)}
    public_train, skipped_train = convert_split(load_json(train_path), tables, "train")
    public_dev, skipped_dev = convert_split(load_json(dev_path), tables, "dev")
    public_train = sample_records(public_train, args.public_train_samples, args.seed)
    public_dev = sample_records(public_dev, args.public_dev_samples, args.seed)

    missing_databases = sorted(
        db_id for db_id in {record["db_id"] for record in public_dev}
        if not (database_dir / db_id / f"{db_id}.sqlite").is_file()
    )
    if missing_databases:
        raise FileNotFoundError(
            "公开评测缺少 SQLite 数据库：" + "、".join(missing_databases[:5])
            + "。请确认 database/<db_id>/<db_id>.sqlite 已完整放入数据目录。"
        )

    domain_records = [] if args.public_only else read_jsonl(args.domain_path)
    combined = public_train + domain_records
    write_jsonl(args.public_train_output, public_train)
    write_jsonl(args.combined_output, combined)
    write_jsonl(args.dev_output, public_dev)

    manifest = {
        "dataset": "CSpider",
        "说明": "固定随机种子抽取的公开训练与 dev 子集；公开数据和电商数据分别评测。",
        "随机种子": args.seed,
        "公开训练样本": len(public_train),
        "电商领域训练样本": len(domain_records),
        "合并训练样本": len(combined),
        "公开dev样本": len(public_dev),
        "转换时跳过训练样本": skipped_train,
        "转换时跳过dev样本": skipped_dev,
    }
    manifest_path = Path(args.manifest_output)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"合并训练快照：{args.combined_output}")
    print(f"公开评测集：{args.dev_output}")


def self_test():
    with tempfile.TemporaryDirectory() as temporary_dir:
        root = Path(temporary_dir)
        database_dir = root / "database" / "concert_singer"
        database_dir.mkdir(parents=True)
        with closing(sqlite3.connect(database_dir / "concert_singer.sqlite")) as connection:
            connection.execute("CREATE TABLE singer (singer_id INTEGER, name TEXT)")
            connection.execute("INSERT INTO singer VALUES (1, 'Alice')")
            connection.commit()

        tables = [{
            "db_id": "concert_singer",
            "table_names_original": ["singer"],
            "column_names_original": [[-1, "*"], [0, "singer_id"], [0, "name"]],
            "foreign_keys": [],
        }]
        item = {"db_id": "concert_singer", "question": "共有多少名歌手？", "query": "SELECT count(*) FROM singer"}
        for name, value in (("tables.json", tables), ("train.json", [item, item]), ("dev.json", [item])):
            (root / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

        domain_path = root / "domain.jsonl"
        domain_record = build_public_record("domain", 0, item, tables[0])
        domain_record["id"] = "domain_1"
        domain_record.pop("db_id")
        write_jsonl(domain_path, [domain_record])
        args = argparse.Namespace(
            source_dir=str(root), database_dir="", domain_path=str(domain_path),
            public_train_output=str(root / "out" / "train.jsonl"),
            combined_output=str(root / "out" / "combined.jsonl"),
            dev_output=str(root / "out" / "dev.jsonl"),
            manifest_output=str(root / "out" / "manifest.json"),
            public_train_samples=10, public_dev_samples=10, seed=42, public_only=False,
        )
        prepare(args)
        assert len(read_jsonl(args.public_train_output)) == 1
        assert len(read_jsonl(args.combined_output)) == 2
        assert len(read_jsonl(args.dev_output)) == 1
        from scripts.train_student import validate_records

        assert len(validate_records(args.combined_output)) == 2
    print("CSpider 数据转换自检通过。")


def main():
    args = parse_args()
    try:
        if args.self_test:
            self_test()
        else:
            prepare(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
