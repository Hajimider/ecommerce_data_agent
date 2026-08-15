ORDER_STATUS_VALUES = ("已完成", "待付款", "退款中", "已取消")


KNOWLEDGE_BASE = [
    {
        "title": "数据库表结构与关联关系",
        "keywords": ("表", "字段", "订单", "商品", "用户", "关联", "明细"),
        "content": """表结构：
users(user_id, name, city, register_date, member_level)
products(product_id, product_name, category, price, stock)
orders(order_id, user_id, order_date, status, total_amount)
order_items(item_id, order_id, product_id, quantity, unit_price)
关联：users.user_id = orders.user_id；orders.order_id = order_items.order_id；products.product_id = order_items.product_id。orders 表没有 product_id，订单与商品必须经由 order_items 关联。""",
    },
    {
        "title": "销售额与销量指标口径",
        "keywords": ("销售额", "销售金额", "营收", "销量", "卖出", "分类", "排行"),
        "content": "销售额统一计算为 SUM(order_items.quantity * order_items.unit_price)，销量计算为 SUM(order_items.quantity)。按商品或分类统计销售指标时，需要使用 products、order_items，若需筛选订单状态再关联 orders。未提到状态时统计全部订单。",
    },
    {
        "title": "订单与用户分析口径",
        "keywords": ("订单", "用户", "城市", "会员", "状态", "已完成", "待付款", "退款", "取消"),
        "content": "订单状态保存在 orders.status，有效值只能使用中文原值：已完成、待付款、退款中、已取消，不能翻译成 completed、pending、refunded 或 cancelled。订单金额保存在 orders.total_amount。用户城市和会员等级保存在 users 表。按城市或用户查询订单时，使用 orders JOIN users ON orders.user_id = users.user_id。",
    },
    {
        "title": "库存与商品分析口径",
        "keywords": ("库存", "价格", "商品", "分类", "低库存"),
        "content": "商品名称、分类、价格和库存都在 products 表。查询库存或商品价格通常只需 products 表，库存字段为 stock，价格字段为 price。",
    },
]


def retrieve(question, top_k=3):
    question = question.lower()
    ranked = []
    for item in KNOWLEDGE_BASE:
        score = sum(keyword.lower() in question for keyword in item["keywords"])
        ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    selected = [item for score, item in ranked[:top_k] if score > 0]
    return selected or [KNOWLEDGE_BASE[0]]


def format_context(items):
    return "\n\n".join(f"【{item['title']}】\n{item['content']}" for item in items)
