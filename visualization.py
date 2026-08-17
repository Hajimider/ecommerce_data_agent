"""使用 Plotly 将电商教学库汇总结果生成交互式 HTML 图表。"""

import argparse
import json
import os
import tempfile
import webbrowser
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from config import Settings, get_settings


CHART_QUERIES = {
    "category_sales": """
        SELECT p.category,
               SUM(oi.quantity) AS sold_quantity,
               SUM(oi.quantity * oi.unit_price) AS sales_amount
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.product_id = p.product_id
        WHERE o.status = %s
        GROUP BY p.category
        ORDER BY sales_amount DESC
    """,
    "city_sales": """
        SELECT u.city,
               SUM(o.total_amount) AS sales_amount,
               AVG(o.total_amount) AS average_order_amount
        FROM orders o
        JOIN users u ON o.user_id = u.user_id
        WHERE o.status = %s
        GROUP BY u.city
        ORDER BY sales_amount DESC
    """,
    "order_status": """
        SELECT status AS order_status, COUNT(*) AS order_count
        FROM orders
        GROUP BY status
        ORDER BY order_count DESC
    """,
    "inventory_value": """
        SELECT product_name, category, price * stock AS inventory_value
        FROM products
        ORDER BY inventory_value DESC
    """,
    "monthly_sales": """
        SELECT DATE_FORMAT(order_date, '%%Y-%%m') AS order_month,
               SUM(total_amount) AS sales_amount
        FROM orders
        WHERE status = %s
        GROUP BY order_month
        ORDER BY order_month
    """,
}

DASHBOARD_FILE = "dashboard.html"
QUERY_CHART_NAMES = {
    "bar": "柱状图",
    "line": "折线图",
    "pie": "饼图",
    "scatter": "散点图",
    "indicator": "指标卡",
    "table": "数据表",
}


def _open_dashboard(path):
    """优先使用 Windows 文件关联打开本地 HTML，避免浏览器只打开默认主页。"""
    resolved = str(path.resolve())
    if os.name == "nt":
        os.startfile(resolved)
    else:
        webbrowser.open(path.resolve().as_uri())


def _connection(settings: Settings):
    import pymysql

    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        autocommit=True,
    )


def _value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _is_number(value):
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def _column_values(rows, index):
    return [row[index] for row in rows if row[index] is not None]


def _looks_temporal(column, values):
    name = column.lower()
    if any(keyword in name for keyword in ("date", "time", "month", "year", "日期", "时间", "月份", "年度")):
        return True
    return bool(values) and all(isinstance(value, (date, datetime)) for value in values)


def choose_query_chart(columns, rows):
    """根据结果结构选择稳定的 Plotly 图表，不让大模型生成绘图代码。"""
    if not columns or not rows:
        return {"kind": "table"}

    numeric = []
    categorical = []
    temporal = []
    for index, column in enumerate(columns):
        values = _column_values(rows, index)
        if values and all(_is_number(value) for value in values):
            numeric.append(index)
        else:
            categorical.append(index)
        if _looks_temporal(column, values):
            temporal.append(index)

    if len(rows) == 1 and len(columns) == 1 and len(numeric) == 1:
        return {"kind": "indicator", "value": numeric[0]}
    if temporal:
        x_index = temporal[0]
        y_index = next((index for index in numeric if index != x_index), None)
        if y_index is not None:
            return {"kind": "line", "x": x_index, "y": y_index}
    if categorical and numeric:
        x_index, y_index = categorical[0], numeric[0]
        names = f"{columns[x_index]} {columns[y_index]}".lower()
        if len(rows) <= 8 and any(keyword in names for keyword in ("status", "type", "状态", "类型")):
            return {"kind": "pie", "x": x_index, "y": y_index}
        return {"kind": "bar", "x": x_index, "y": y_index}
    if len(numeric) >= 2:
        return {"kind": "scatter", "x": numeric[0], "y": numeric[1]}
    return {"kind": "table"}


def _query_figure(question, columns, rows, chart):
    import plotly.graph_objects as go

    normalized_rows = [[_value(value) for value in row] for row in rows]
    kind = chart["kind"]
    if kind == "indicator":
        index = chart["value"]
        column = columns[index]
        title = {
            "average_amount": "平均订单金额",
            "average_order_amount": "平均订单金额",
            "total_amount": "订单总金额",
            "sales_amount": "销售额",
            "order_count": "订单数",
        }.get(column.lower(), column)
        indicator_text = f"{question} {column}".lower()
        is_money = any(keyword in indicator_text for keyword in ("amount", "revenue", "sales", "price", "金额", "销售额", "营收", "收入", "价格"))
        number = {"prefix": "¥", "valueformat": ",.2f"} if is_money else {}
        return go.Figure(go.Indicator(mode="number", value=normalized_rows[0][index], number=number, title={"text": title}))
    if kind == "table":
        values = [[row[index] for row in normalized_rows] for index in range(len(columns))]
        return go.Figure(go.Table(header={"values": columns}, cells={"values": values}))

    x_index, y_index = chart["x"], chart["y"]
    x_values = [row[x_index] for row in normalized_rows]
    y_values = [row[y_index] for row in normalized_rows]
    if kind == "line":
        figure = go.Figure(go.Scatter(x=x_values, y=y_values, mode="lines+markers"))
    elif kind == "pie":
        figure = go.Figure(go.Pie(labels=x_values, values=y_values, hole=0.35))
    elif kind == "scatter":
        figure = go.Figure(go.Scatter(x=x_values, y=y_values, mode="markers"))
    else:
        figure = go.Figure(go.Bar(x=x_values, y=y_values))
    figure.update_xaxes(title_text=columns[x_index])
    figure.update_yaxes(title_text=columns[y_index])
    figure.update_layout(title_text=question)
    return figure


def build_query_figure(question, columns, rows):
    """根据查询结果构建可直接嵌入页面的 Plotly 图表。"""
    if not rows or not any(value is not None for row in rows for value in row):
        raise ValueError("查询结果为空或只有 NULL，请检查 SQL 的筛选条件")
    chart = choose_query_chart(columns, rows)
    figure = _query_figure(question, columns, rows, chart)
    figure.update_layout(
        title_text=question,
        template="plotly_white",
        margin={"l": 60, "r": 30, "t": 80, "b": 60},
    )
    return figure, {"kind": chart["kind"], "name": QUERY_CHART_NAMES[chart["kind"]]}


def export_query_chart(question, columns, rows, output_dir="outputs/charts/queries", open_browser=True):
    """将一次 Agent 查询结果导出为独立 HTML，并按需自动打开。"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    figure, chart = build_query_figure(question, columns, rows)
    chart_path = output_path / f"query_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.html"
    figure.write_html(chart_path, full_html=True, include_plotlyjs="directory")
    if open_browser:
        _open_dashboard(chart_path)
    return {"path": str(chart_path), **chart}


def _query(settings, sql, params=()):
    connection = _connection(settings)
    try:
        with connection.cursor() as cursor:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            columns = [item[0] for item in cursor.description or []]
            return columns, [[_value(value) for value in row] for row in cursor.fetchall()]
    finally:
        connection.close()


def _figure(kind, columns, rows):
    import plotly.graph_objects as go

    data = {column: [row[index] for row in rows] for index, column in enumerate(columns)}
    if kind == "category_sales":
        return go.Figure(go.Bar(x=data["category"], y=data["sales_amount"], name="销售额"), layout_title_text="各商品分类销售额")
    if kind == "city_sales":
        return go.Figure(go.Bar(x=data["city"], y=data["sales_amount"], name="销售额"), layout_title_text="各城市销售额")
    if kind == "order_status":
        return go.Figure(go.Pie(labels=data["order_status"], values=data["order_count"], hole=0.35), layout_title_text="订单状态分布")
    if kind == "inventory_value":
        return go.Figure(go.Bar(x=data["product_name"], y=data["inventory_value"], name="库存金额"), layout_title_text="商品库存金额")
    if kind == "monthly_sales":
        return go.Figure(go.Scatter(x=data["order_month"], y=data["sales_amount"], mode="lines+markers", name="销售额"), layout_title_text="月度销售额趋势")
    raise ValueError(f"未知图表类型：{kind}")


def export_charts(settings=None, output_dir="outputs/charts", completed_status="已完成", open_browser=False):
    settings = settings or get_settings()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    for stale_name in (f"{name}.html" for name in CHART_QUERIES):
        stale_file = output_path / stale_name
        if stale_file.exists():
            stale_file.unlink()
    manifest = {"database": settings.mysql_database, "completed_status": completed_status, "dashboard": DASHBOARD_FILE, "charts": {}}
    html_sections = []
    for name, sql in CHART_QUERIES.items():
        params = (completed_status,) if "%s" in sql else ()
        columns, rows = _query(settings, sql, params)
        figure = _figure(name, columns, rows)
        figure.update_layout(template="plotly_white", margin={"l": 50, "r": 30, "t": 70, "b": 50})
        html_sections.append(
            f'<section class="chart"><h2>{figure.layout.title.text}</h2>'
            f'{figure.to_html(full_html=False, include_plotlyjs=False)}</section>'
        )
        manifest["charts"][name] = {"rows": len(rows), "columns": columns}
    dashboard = output_path / DASHBOARD_FILE
    dashboard.write_text(
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>电商数据分析总览</title><script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script>"
        "<style>body{margin:0;background:#f5f7fa;color:#1f2937;font-family:Arial,'Microsoft YaHei',sans-serif}"
        ".page{max-width:1280px;margin:0 auto;padding:24px}.chart{background:#fff;margin:0 0 20px;padding:8px 16px 16px;border:1px solid #e5e7eb;border-radius:8px}"
        "h1{font-size:24px;margin:0 0 20px}h2{font-size:18px;margin:8px 0}</style></head>"
        f"<body><main class=\"page\"><h1>电商数据分析总览</h1>{''.join(html_sections)}</main></body></html>",
        encoding="utf-8",
    )
    if open_browser:
        _open_dashboard(dashboard)
    (output_path / "index.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def self_test():
    from unittest.mock import patch

    assert set(CHART_QUERIES) == {"category_sales", "city_sales", "order_status", "inventory_value", "monthly_sales"}
    assert all(query.lstrip().upper().startswith("SELECT") for query in CHART_QUERIES.values())
    assert sum("%s" in query for query in CHART_QUERIES.values()) == 3
    assert "'%%Y-%%m'" in CHART_QUERIES["monthly_sales"]
    assert choose_query_chart(["category", "sales"], [["办公设备", Decimal("100")]])["kind"] == "bar"
    assert choose_query_chart(["order_month", "sales"], [["2025-01", Decimal("100")]])["kind"] == "line"
    assert choose_query_chart(["year", "sales"], [[2025, Decimal("100")]]) == {"kind": "line", "x": 0, "y": 1}
    assert choose_query_chart(["status", "order_count"], [["已完成", 3]])["kind"] == "pie"
    assert choose_query_chart(["average_amount"], [[Decimal("100")]])["kind"] == "indicator"
    indicator = _query_figure(
        "计算已完成订单的平均金额",
        ["average_amount"],
        [[Decimal("405.875")]],
        {"kind": "indicator", "value": 0},
    ).data[0]
    assert indicator.title.text == "平均订单金额"
    assert indicator.number.prefix == "¥" and indicator.number.valueformat == ",.2f"
    assert choose_query_chart(["product_name"], [["显示器"]])["kind"] == "table"
    figure, chart = build_query_figure(
        "测试分类销售额",
        ["category", "sales"],
        [["办公设备", Decimal("100")], ["手机配件", Decimal("80")]],
    )
    assert chart == {"kind": "bar", "name": "柱状图"}
    assert figure.layout.title.text == "测试分类销售额"
    try:
        export_query_chart("空指标", ["average_amount"], [[None]], open_browser=False)
    except ValueError:
        pass
    else:
        raise AssertionError("全 NULL 查询结果不应生成图表")
    with tempfile.TemporaryDirectory() as output_dir:
        with patch(f"{__name__}._open_dashboard") as open_dashboard:
            result = export_query_chart(
                "测试分类销售额",
                ["category", "sales"],
                [["办公设备", Decimal("100")], ["手机配件", Decimal("80")]],
                output_dir=output_dir,
                open_browser=True,
            )
            open_dashboard.assert_called_once()
        assert result["kind"] == "bar"
        assert Path(result["path"]).is_file()
        assert (Path(output_dir) / "plotly.min.js").is_file()
    print("Plotly 自检通过：固定总览与查询结果自动选图规则正常。")


def main():
    parser = argparse.ArgumentParser(description="生成 Plotly 交互式电商分析图表")
    parser.add_argument("--output-dir", default="outputs/charts")
    parser.add_argument("--completed-status", default="已完成")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    print(json.dumps(export_charts(output_dir=args.output_dir, completed_status=args.completed_status, open_browser=args.open_browser), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
