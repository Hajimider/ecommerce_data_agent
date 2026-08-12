import argparse
import sys

from agent import EcommerceDataAgent
from config import get_settings
from database import format_sql, format_table, normalize_select
from knowledge import retrieve
from llm_client import create_llm_client


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def self_test():
    assert retrieve("按分类统计销售额")[0]["title"] == "销售额与销量指标口径"
    assert normalize_select("SELECT * FROM products") == "SELECT * FROM products;"
    assert "\nJOIN " in format_sql("SELECT p.category, SUM(oi.quantity) AS sales FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.category ORDER BY sales DESC;")
    try:
        normalize_select("DELETE FROM products")
    except ValueError:
        print("自检通过：知识检索与 SQL 安全校验正常。")
        return
    raise AssertionError("危险 SQL 未被拒绝")


def print_result(result):
    print("\n===== 检索到的业务知识 =====")
    print("、".join(result.sources))
    print("\n===== 执行的 SQL =====")
    print(format_sql(result.sql))
    print("\n===== 查询结果 =====")
    print(format_table(result.columns, result.rows))
    if result.truncated:
        print("结果超过 100 行，仅展示前 100 行。")
    if result.retried:
        print("SQL 首次执行失败，Agent 已自动修复并重试一次。")
    print("\n===== 数据分析结论 =====")
    print(result.answer)


def main():
    parser = argparse.ArgumentParser(description="电商数据分析 Agent")
    parser.add_argument("--question", default="", help="要分析的中文问题")
    parser.add_argument("--self-test", action="store_true", help="不调用 API 的基础自检")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    settings = get_settings()
    agent = EcommerceDataAgent(settings, create_llm_client(settings))
    if args.question:
        print_result(agent.ask(args.question))
        return
    print("电商数据分析 Agent 已启动，输入 exit 退出。")
    while True:
        question = input("\n请输入分析问题：").strip()
        if question.lower() in {"exit", "quit", "退出"}:
            return
        try:
            print_result(agent.ask(question))
        except Exception as exc:
            print(f"执行失败：{exc}")


if __name__ == "__main__":
    main()
