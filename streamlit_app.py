"""电商 Text-to-SQL 微调与 Agent 浏览器 Demo。"""

import json
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from agent import EcommerceDataAgent
from config import get_settings
from database import format_sql
from llm_client import create_llm_client
from visualization import build_query_figure
import os
from dotenv import load_dotenv, find_dotenv

find_dotenv()
load_dotenv()

_=load_dotenv(find_dotenv())

st.set_page_config(
    page_title="电商 Text-to-SQL 微调 Demo",
    page_icon=":material/database:",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "outputs" / "evaluation_fixed_epoch2.json"
BACKENDS = {
    "LoRA 微调模型": "lora",
    "本地基础模型": "base",
    "API 模型": "api",
}
EXAMPLE_QUESTIONS = [
    "统计每位用户有多少个订单，没有订单的用户也要显示",
    "计算已完成订单里每个商品的销售额",
    "统计各商品分类的销售额并按销售额降序排列",
    "按城市统计已完成订单的销售额",
    "按月份统计全部订单金额",
    "统计每种订单状态的订单数量",
    "查询已完成订单中销量最高的 3 个商品",
    "查询库存少于 30 件的商品，按库存升序排列",
    "统计每位用户的订单总金额，按总金额降序排列",
    "计算已完成订单的平均金额",
]
COMPARISON_CASES = [
    {
        "title": "用户订单数统计",
        "question": "统计每位用户有多少个订单，没有订单的用户也要显示",
        "base_sql": """SELECT
    u.user_id,
    COUNT(o.order_id) AS num_orders
FROM users u
LEFT JOIN orders o ON u.user_id = o.user_id
GROUP BY u.user_id;""",
        "base_columns": ["user_id", "num_orders"],
        "base_rows": [[1, 2], [2, 2], [3, 2], [4, 2], [5, 1], [6, 1], [7, 1], [8, 1]],
        "base_correct": False,
        "lora_sql": """SELECT
    u.name,
    COUNT(o.order_id) AS order_count
FROM users u
LEFT JOIN orders o ON u.user_id = o.user_id
GROUP BY u.user_id, u.name
ORDER BY order_count DESC;""",
        "lora_columns": ["name", "order_count"],
        "lora_rows": [["张伟", 2], ["李娜", 2], ["王磊", 2], ["赵敏", 2], ["陈晨", 1], ["刘洋", 1], ["周婷", 1], ["孙浩", 1]],
        "lora_correct": True,
    },
    {
        "title": "已完成订单商品销售额",
        "question": "计算已完成订单里每个商品的销售额",
        "base_sql": """SELECT
    p.product_name,
    SUM(oi.quantity * oi.unit_price) AS sales
FROM orders o
JOIN users u ON o.user_id = u.user_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.status = '已完成'
GROUP BY p.product_name;""",
        "base_columns": ["product_name", "sales"],
        "base_rows": [["蓝牙耳机", 597.00], ["机械键盘", 329.00], ["保温杯", 138.00], ["手机支架", 78.00], ["充电宝", 447.00], ["显示器", 1299.00], ["无线鼠标", 89.00], ["台灯", 318.00]],
        "base_correct": True,
        "lora_sql": """SELECT
    p.product_name,
    SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE o.status = '已完成'
GROUP BY p.product_id, p.product_name
ORDER BY total_revenue DESC;""",
        "lora_columns": ["product_name", "total_revenue"],
        "lora_rows": [["显示器", 1299.00], ["蓝牙耳机", 597.00], ["充电宝", 447.00], ["机械键盘", 329.00], ["台灯", 318.00], ["保温杯", 138.00], ["无线鼠标", 89.00], ["手机支架", 78.00]],
        "lora_correct": True,
    },
]


def backend_settings(backend):
    settings = get_settings()
    mode = BACKENDS[backend]
    if mode == "api":
        if not settings.api_key:
            raise ValueError("API 模式缺少 LLM_API_KEY，请先在 .env 中配置。")
        return replace(settings, mode="api")
    if not settings.local_model_path:
        raise ValueError("本地模式缺少 LOCAL_MODEL_PATH，请先在 .env 中配置。")
    if mode == "lora" and not settings.local_adapter_path:
        raise ValueError("LoRA 模式缺少 LOCAL_ADAPTER_PATH，请先在 .env 中配置。")
    adapter = settings.local_adapter_path if mode == "lora" else ""
    return replace(settings, mode="local", local_adapter_path=adapter)


@st.cache_resource(max_entries=1, show_spinner=False)
def load_agent(settings):
    return EcommerceDataAgent(settings, create_llm_client(settings))


@st.cache_data
def load_report(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def percentage(value):
    return f"{value * 100:.2f}%"


def render_live_result(record):
    result = record["result"]
    first_row = st.columns(2)
    first_row[0].metric("模型", record["backend"], border=True)
    first_row[1].metric("查询行数", len(result.rows), border=True)
    second_row = st.columns(2)
    second_row[0].metric("总耗时", f"{record['seconds']:.2f} 秒", border=True)
    second_row[1].metric("SQL 重试", "是" if result.retried else "否", border=True)

    with st.container(border=True):
        st.subheader("分析结论")
        st.write(result.answer)

    with st.container(border=True):
        st.subheader("执行 SQL")
        st.code(format_sql(result.sql), language="sql")

    if result.truncated:
        st.warning("查询结果超过 100 行，当前只展示前 100 行。", icon=":material/warning:")
    frame = pd.DataFrame(result.rows, columns=result.columns)
    with st.container(border=True):
        st.subheader("查询结果")
        st.dataframe(frame, hide_index=True, key="query_result")

    try:
        figure, chart = build_query_figure(record["question"], result.columns, result.rows)
    except ValueError as exc:
        st.info(str(exc), icon=":material/info:")
    else:
        with st.container(border=True):
            st.subheader(f"自动图表 · {chart['name']}")
            st.plotly_chart(figure, width="stretch", key="query_chart")

    with st.expander("检索到的业务知识", icon=":material/menu_book:"):
        st.write("、".join(result.sources))


def render_demo_case(case, index):
    st.subheader(f"{index}. {case['title']}")
    st.caption(case["question"])
    base_column, lora_column = st.columns(2)
    with base_column.container(border=True, height="stretch"):
        st.markdown("**本地基础模型**")
        st.code(case["base_sql"], language="sql")
        st.badge(
            "结果正确" if case["base_correct"] else "结果错误",
            color="green" if case["base_correct"] else "red",
            icon=":material/check:" if case["base_correct"] else ":material/close:",
        )
        st.dataframe(
            pd.DataFrame(case["base_rows"], columns=case["base_columns"]),
            hide_index=True,
            key=f"demo_case_{index}_base",
        )
    with lora_column.container(border=True, height="stretch"):
        st.markdown("**LoRA 微调模型**")
        st.code(case["lora_sql"], language="sql")
        st.badge(
            "结果正确" if case["lora_correct"] else "结果错误",
            color="green" if case["lora_correct"] else "red",
            icon=":material/check:" if case["lora_correct"] else ":material/close:",
        )
        st.dataframe(
            pd.DataFrame(case["lora_rows"], columns=case["lora_columns"]),
            hide_index=True,
            key=f"demo_case_{index}_lora",
        )


def render_comparison():
    if not REPORT_PATH.is_file():
        st.error("找不到评估报告 outputs/evaluation_fixed_epoch2.json。", icon=":material/error:")
        return
    report = load_report(str(REPORT_PATH))["结果"]
    base = report["本地基础模型"]
    lora = report["LoRA学生模型"]
    gain = lora["执行结果正确率"] - base["执行结果正确率"]

    metrics = st.columns(3)
    metrics[0].metric("基础模型结果正确率", percentage(base["执行结果正确率"]), border=True)
    metrics[1].metric("LoRA 结果正确率", percentage(lora["执行结果正确率"]), border=True)
    metrics[2].metric("正确率提升", f"+{gain * 100:.2f} 个百分点", border=True)

    comparison = pd.DataFrame(
        [
            {
                "模型": "本地基础模型",
                "样本数": base["样本数"],
                "SQL 可执行率": percentage(base["SQL可执行率"]),
                "执行结果正确率": percentage(base["执行结果正确率"]),
                "Agent 首次成功率": percentage(base["Agent首次成功率"]),
            },
            {
                "模型": "LoRA 微调模型",
                "样本数": lora["样本数"],
                "SQL 可执行率": percentage(lora["SQL可执行率"]),
                "执行结果正确率": percentage(lora["执行结果正确率"]),
                "Agent 首次成功率": percentage(lora["Agent首次成功率"]),
            },
        ]
    )
    with st.container(border=True):
        st.subheader("固定测试集评估")
        st.dataframe(comparison, hide_index=True, key="evaluation_comparison")
        st.caption("结果来自 24 条未参与训练的电商独立测试题，当前展示 epoch2 LoRA。")

    st.subheader("双题实际运行记录")
    st.caption("第一题展示微调后的字段与分组修正，第二题展示多表销售额关联；结果来自本地固定 epoch2 适配器的实际运行记录。")
    for index, case in enumerate(COMPARISON_CASES, start=1):
        render_demo_case(case, index)
    st.caption("单次耗时受模型加载、缓存和 CPU 状态影响，不作为推理性能结论。")


st.title("Text-to-SQL 微调 Demo")
st.caption("Qwen LoRA 微调效果与单个 Text-to-SQL Agent 查询展示")

view = st.segmented_control(
    "展示内容",
    ["在线查询", "微调对比"],
    default="在线查询",
    required=True,
    width="stretch",
)

if view == "微调对比":
    render_comparison()
else:
    with st.sidebar:
        st.subheader("运行配置")
        backend = st.selectbox("模型后端", list(BACKENDS), index=0)
        st.caption("模型和数据库连接信息从项目根目录的 .env 读取。")
        if st.button("释放模型缓存", icon=":material/delete_sweep:"):
            load_agent.clear()
            st.toast("模型缓存已释放。")

    with st.form("query_form", border=True):
        question = st.selectbox(
            "自然语言问题",
            EXAMPLE_QUESTIONS,
            accept_new_options=True,
            placeholder="选择示例或输入自己的问题",
        )
        submitted = st.form_submit_button(
            "开始分析",
            type="primary",
            icon=":material/play_arrow:",
        )

    if submitted:
        try:
            settings = backend_settings(backend)
            with st.status("正在生成并执行 SQL", expanded=True) as status:
                started = time.perf_counter()
                agent = load_agent(settings)
                status.write("模型已就绪，正在理解问题和业务表结构。")
                result = agent.ask(question)
                seconds = time.perf_counter() - started
                status.update(label="查询完成", state="complete", expanded=False)
            st.session_state["last_query"] = {
                "backend": backend,
                "question": question,
                "seconds": seconds,
                "result": result,
            }
        except Exception as exc:
            st.error(f"查询失败：{exc}", icon=":material/error:")

    if "last_query" in st.session_state:
        render_live_result(st.session_state["last_query"])
