import json
import re
from dataclasses import dataclass

from database import execute_select, normalize_select
from knowledge import ORDER_STATUS_VALUES, format_context, retrieve


SQL_SYSTEM = """你是电商数据分析 Agent 的 SQL 工具规划器。依据给出的业务知识回答用户问题。
只返回一个 JSON 对象，格式为 {"sql":"一条 SELECT SQL;"}，不要 Markdown 或其他文字。
只允许 SELECT；不确定时也不能编造字段。"""

ANSWER_SYSTEM = """你是电商数据分析助手。根据用户问题和已执行 SQL 的结果，用简洁中文说明结论。
不得虚构数据；若结果为空，明确说明未查询到数据。不要重复整段 SQL。"""


@dataclass
class AgentResult:
    sources: list
    sql: str
    columns: list
    rows: list
    truncated: bool
    answer: str
    retried: bool


def extract_plan(text):
    text = text.replace("```json", "").replace("```", "").strip()
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            data, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "sql" in data:
            return normalize_select(data["sql"])
    raise ValueError("模型没有返回合法的 JSON 决策")


def validate_business_sql(sql):
    status_pattern = re.compile(r"\b(?:\w+\.)?status\s*=\s*(['\"])(.*?)\1", re.I)
    invalid_values = [match.group(2) for match in status_pattern.finditer(sql) if match.group(2) not in ORDER_STATUS_VALUES]
    if invalid_values:
        allowed = "、".join(ORDER_STATUS_VALUES)
        raise ValueError(f"orders.status 使用了无效值 {invalid_values[0]!r}，只能使用：{allowed}")
    return sql


class EcommerceDataAgent:
    def __init__(self, settings, client):
        self.settings = settings
        self.client = client

    def _plan(self, question, context, error=""):
        repair_note = f"\n上一条 SQL 执行失败：{error}\n请仅修复 SQL。" if error else ""
        text = self.client.chat(SQL_SYSTEM, f"业务知识：\n{context}\n\n用户问题：{question}{repair_note}")
        return validate_business_sql(extract_plan(text))

    def ask(self, question):
        question = question.strip()
        if not question:
            raise ValueError("问题不能为空")
        sources = retrieve(question)
        context = format_context(sources)
        retried = False
        try:
            sql = self._plan(question, context)
            columns, rows, truncated = execute_select(self.settings, sql)
        except Exception as first_error:
            retried = True
            sql = self._plan(question, context, str(first_error))
            columns, rows, truncated = execute_select(self.settings, sql)
        result_text = json.dumps({"columns": columns, "rows": rows, "truncated": truncated}, ensure_ascii=False, default=str)
        answer = self.client.chat(ANSWER_SYSTEM, f"用户问题：{question}\n已执行 SQL：{sql}\n查询结果：{result_text}")
        return AgentResult([item["title"] for item in sources], sql, columns, rows, truncated, answer, retried)
