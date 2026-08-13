"""使用 Plotly 将电商教学库汇总结果生成交互式 HTML 图表。"""

import argparse
import json
import os
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
    assert set(CHART_QUERIES) == {"category_sales", "city_sales", "order_status", "inventory_value", "monthly_sales"}
    assert all(query.lstrip().upper().startswith("SELECT") for query in CHART_QUERIES.values())
    assert sum("%s" in query for query in CHART_QUERIES.values()) == 3
    assert "'%%Y-%%m'" in CHART_QUERIES["monthly_sales"]
    print("Plotly 自检通过：5 个固定 SELECT 图表查询均已定义。")


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
