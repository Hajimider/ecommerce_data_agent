import json
from pathlib import Path

from agent import SQL_SYSTEM
from database import normalize_select
from knowledge import format_context, retrieve


SEED_TASKS = [
    ("seed_status_count", "统计已完成订单的数量", "SELECT COUNT(*) AS order_count FROM orders WHERE status = '已完成';"),
    ("seed_category_price", "列出办公设备分类的商品名称和价格，按价格从高到低排列", "SELECT product_name, price FROM products WHERE category = '办公设备' ORDER BY price DESC;"),
    ("seed_low_stock", "查询库存少于 30 件的商品，按库存升序排列", "SELECT product_name, stock FROM products WHERE stock < 30 ORDER BY stock ASC;"),
    ("seed_user_orders", "查询张伟的全部订单，按下单日期排列", "SELECT o.order_id, o.order_date, o.status, o.total_amount FROM orders o JOIN users u ON o.user_id = u.user_id WHERE u.name = '张伟' ORDER BY o.order_date;"),
    ("seed_city_orders", "列出上海用户的订单编号、姓名和金额，金额高的排在前面", "SELECT o.order_id, u.name, o.total_amount FROM orders o JOIN users u ON o.user_id = u.user_id WHERE u.city = '上海' ORDER BY o.total_amount DESC;"),
    ("seed_member_count", "统计每个会员等级的用户数量", "SELECT member_level, COUNT(*) AS user_count FROM users GROUP BY member_level ORDER BY user_count DESC;"),
    ("seed_city_revenue", "按城市统计已完成订单的销售额", "SELECT u.city, SUM(o.total_amount) AS total_revenue FROM orders o JOIN users u ON o.user_id = u.user_id WHERE o.status = '已完成' GROUP BY u.city ORDER BY total_revenue DESC;"),
    ("seed_top_products", "查询已完成订单中销量最高的 3 个商品", "SELECT p.product_name, SUM(oi.quantity) AS sold_quantity FROM order_items oi JOIN products p ON oi.product_id = p.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = '已完成' GROUP BY p.product_id, p.product_name ORDER BY sold_quantity DESC LIMIT 3;"),
    ("seed_category_revenue", "统计已完成订单中各商品分类的销售额", "SELECT p.category, SUM(oi.quantity * oi.unit_price) AS total_revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = '已完成' GROUP BY p.category ORDER BY total_revenue DESC;"),
    ("seed_recent_orders", "查询 2025 年 3 月 1 日之后的已完成订单编号和金额", "SELECT order_id, total_amount FROM orders WHERE status = '已完成' AND order_date >= '2025-03-01' ORDER BY order_date;"),
    ("seed_status_average", "计算每种订单状态的平均订单金额", "SELECT status, AVG(total_amount) AS average_amount FROM orders GROUP BY status ORDER BY average_amount DESC;"),
    ("seed_unsold_products", "找出从未出现在订单明细中的商品", "SELECT p.product_name FROM products p LEFT JOIN order_items oi ON p.product_id = oi.product_id WHERE oi.item_id IS NULL ORDER BY p.product_id;"),
    ("seed_user_spend", "统计每位用户的订单总金额，按总金额降序排列", "SELECT u.name, SUM(o.total_amount) AS total_spend FROM users u JOIN orders o ON u.user_id = o.user_id GROUP BY u.user_id, u.name ORDER BY total_spend DESC;"),
    ("seed_month_revenue", "按月份统计全部订单金额", "SELECT DATE_FORMAT(order_date, '%Y-%m') AS order_month, SUM(total_amount) AS total_amount FROM orders GROUP BY order_month ORDER BY order_month;"),
    ("seed_completed_average", "计算已完成订单的平均金额", "SELECT AVG(total_amount) AS average_amount FROM orders WHERE status = '已完成';"),
]


HUMAN_TEST_CASES = [
    ("test_category_max_price", "分别找出每个商品分类中的最高售价", "SELECT category, MAX(price) AS max_price FROM products GROUP BY category ORDER BY category;"),
    ("test_refund_orders", "列出退款中的订单编号、日期和金额", "SELECT order_id, order_date, total_amount FROM orders WHERE status = '退款中' ORDER BY order_date;"),
    ("test_user_order_count", "统计每位用户有多少个订单，没有订单的用户也要显示", "SELECT u.name, COUNT(o.order_id) AS order_count FROM users u LEFT JOIN orders o ON u.user_id = o.user_id GROUP BY u.user_id, u.name ORDER BY order_count DESC, u.user_id;"),
    ("test_category_units", "统计各商品分类累计卖出的件数", "SELECT p.category, SUM(oi.quantity) AS sold_quantity FROM products p JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.category ORDER BY sold_quantity DESC;"),
    ("test_registered_users", "查询 2024 年 6 月 1 日以后注册的用户姓名和会员等级", "SELECT name, member_level FROM users WHERE register_date >= '2024-06-01' ORDER BY register_date;"),
    ("test_order_detail", "查看订单 1004 包含的商品名称、数量和成交单价", "SELECT p.product_name, oi.quantity, oi.unit_price FROM order_items oi JOIN products p ON oi.product_id = p.product_id WHERE oi.order_id = 1004 ORDER BY oi.item_id;"),
    ("test_completed_month_count", "按月份统计已完成订单数", "SELECT DATE_FORMAT(order_date, '%Y-%m') AS order_month, COUNT(*) AS order_count FROM orders WHERE status = '已完成' GROUP BY order_month ORDER BY order_month;"),
    ("test_high_value_users", "找出订单总金额超过 500 元的用户", "SELECT u.name, SUM(o.total_amount) AS total_spend FROM users u JOIN orders o ON u.user_id = o.user_id GROUP BY u.user_id, u.name HAVING total_spend > 500 ORDER BY total_spend DESC;"),
    ("test_product_order_count", "统计每个商品出现在多少个不同订单中", "SELECT p.product_name, COUNT(DISTINCT oi.order_id) AS order_count FROM products p LEFT JOIN order_items oi ON p.product_id = oi.product_id GROUP BY p.product_id, p.product_name ORDER BY order_count DESC, p.product_id;"),
    ("test_completed_product_revenue", "计算已完成订单里每个商品的销售额", "SELECT p.product_name, SUM(oi.quantity * oi.unit_price) AS revenue FROM products p JOIN order_items oi ON p.product_id = oi.product_id JOIN orders o ON oi.order_id = o.order_id WHERE o.status = '已完成' GROUP BY p.product_id, p.product_name ORDER BY revenue DESC;"),
    ("test_beijing_completed", "查询北京用户已经完成的订单编号和金额", "SELECT o.order_id, o.total_amount FROM orders o JOIN users u ON o.user_id = u.user_id WHERE u.city = '北京' AND o.status = '已完成' ORDER BY o.order_date;"),
    ("test_stock_value", "计算每个商品的库存金额并按金额降序排列", "SELECT product_name, price * stock AS stock_value FROM products ORDER BY stock_value DESC;"),
    ("test_city_user_count", "统计每个城市的用户数量，按人数降序排列", "SELECT city, COUNT(*) AS user_count FROM users GROUP BY city ORDER BY user_count DESC, city;"),
    ("test_category_average_price", "计算各商品分类的平均售价并按均价降序排列", "SELECT category, AVG(price) AS average_price FROM products GROUP BY category ORDER BY average_price DESC;"),
    ("test_multi_product_orders", "找出包含至少两种不同商品的订单", "SELECT o.order_id, COUNT(DISTINCT oi.product_id) AS product_count FROM orders o JOIN order_items oi ON o.order_id = oi.order_id GROUP BY o.order_id HAVING product_count >= 2 ORDER BY product_count DESC, o.order_id;"),
    ("test_users_without_completed_orders", "查询没有任何已完成订单的用户姓名", "SELECT u.name FROM users u LEFT JOIN orders o ON u.user_id = o.user_id AND o.status = '已完成' WHERE o.order_id IS NULL ORDER BY u.user_id;"),
    ("test_latest_order_date", "查询每位下过单用户的最近下单日期", "SELECT u.name, MAX(o.order_date) AS latest_order_date FROM users u JOIN orders o ON u.user_id = o.user_id GROUP BY u.user_id, u.name ORDER BY latest_order_date DESC, u.user_id;"),
    ("test_completed_order_item_count", "统计每个已完成订单包含的明细行数", "SELECT o.order_id, COUNT(oi.item_id) AS item_count FROM orders o JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status = '已完成' GROUP BY o.order_id ORDER BY item_count DESC, o.order_id;"),
    ("test_beijing_product_quantity", "统计北京用户购买过的各商品数量", "SELECT p.product_name, SUM(oi.quantity) AS purchased_quantity FROM users u JOIN orders o ON u.user_id = o.user_id JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id WHERE u.city = '北京' GROUP BY p.product_id, p.product_name ORDER BY purchased_quantity DESC, p.product_id;"),
    ("test_category_average_stock", "计算每个商品分类的平均库存量", "SELECT category, AVG(stock) AS average_stock FROM products GROUP BY category ORDER BY average_stock DESC;"),
    ("test_order_amount_range", "查询金额在 100 元到 400 元之间的订单", "SELECT order_id, total_amount FROM orders WHERE total_amount BETWEEN 100 AND 400 ORDER BY total_amount DESC, order_id;"),
    ("test_gold_completed_revenue", "统计每位黄金会员已完成订单的总金额", "SELECT u.name, SUM(o.total_amount) AS completed_amount FROM users u JOIN orders o ON u.user_id = o.user_id WHERE u.member_level = '黄金' AND o.status = '已完成' GROUP BY u.user_id, u.name ORDER BY completed_amount DESC, u.user_id;"),
    ("test_above_average_price", "列出售价高于全部商品平均售价的商品", "SELECT product_name, price FROM products WHERE price > (SELECT AVG(price) FROM products) ORDER BY price DESC;"),
    ("test_cancelled_order_products", "列出已取消订单中的商品名称和购买数量", "SELECT o.order_id, p.product_name, oi.quantity FROM orders o JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id WHERE o.status = '已取消' ORDER BY oi.item_id;"),
]


def build_user_prompt(question):
    context = format_context(retrieve(question))
    return f"业务知识：\n{context}\n\n用户问题：{question.strip()}"


def build_record(record_id, question, sql, source, seed_id=""):
    sql = normalize_select(sql)
    return {
        "id": record_id,
        "source": source,
        "seed_id": seed_id or record_id,
        "question": question.strip(),
        "sql": sql,
        "messages": [
            {"role": "system", "content": SQL_SYSTEM},
            {"role": "user", "content": build_user_prompt(question)},
            {"role": "assistant", "content": json.dumps({"sql": sql}, ensure_ascii=False, separators=(",", ":"))},
        ],
    }


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path):
    records = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"第 {line_number} 行不是合法 JSON") from exc
    return records
