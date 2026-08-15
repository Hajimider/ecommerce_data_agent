"""IDE 一键启动入口。

在本文件开头修改配置后，直接右键运行本文件即可。
敏感配置留空时读取项目根目录的 .env 文件。
"""

import os
import sys

from app import main


# 运行方式：api 调用云端模型；local 加载本地模型。二选一。
LLM_MODE = "api"

# 留空表示读取 .env；填写后只覆盖本次运行，不会写回文件。
LLM_API_BASE = ""
LLM_API_KEY = ""
LLM_MODEL = ""
LLM_CA_BUNDLE = ""

# 本地模型配置：仅当 LLM_MODE = "local" 时生效。
LOCAL_MODEL_PATH = ""
LOCAL_ADAPTER_PATH = ""
LOCAL_THREADS = "8"
LOCAL_MAX_NEW_TOKENS = "256"

# MySQL 连接配置。密码留空表示读取 .env。
MYSQL_HOST = ""
MYSQL_PORT = ""
MYSQL_USER = ""
MYSQL_PASSWORD = ""
MYSQL_DATABASE = ""

# 填入问题后，IDE 每次运行直接执行该问题；留空则进入连续提问模式。
TEST_QUESTIONS = [
    "统计各商品分类的销售额并按销售额降序排列",  # 柱状图
    "按城市统计已完成订单的销售额",              # 柱状图
    "按月份统计全部订单金额",                    # 折线图
    "统计每种订单状态的订单数量",                # 饼图
    "查询已完成订单中销量最高的 3 个商品",         # 柱状图
    "查询库存少于 30 件的商品，按库存升序排列",    # 柱状图
    "统计每位用户的订单总金额，按总金额降序排列",  # 柱状图
    "计算已完成订单的平均金额",                  # 指标卡
]
QUESTION = TEST_QUESTIONS[4]

# 查询成功后自动生成独立 Plotly HTML；OPEN_CHART=True 时同时打开浏览器。
AUTO_CHART = True
OPEN_CHART = True
CHART_OUTPUT_DIR = "outputs/charts/queries"


def apply_config():
    config = {
        "LLM_MODE": LLM_MODE,
        "LLM_API_BASE": LLM_API_BASE,
        "LLM_API_KEY": LLM_API_KEY,
        "LLM_MODEL": LLM_MODEL,
        "LLM_CA_BUNDLE": LLM_CA_BUNDLE,
        "LOCAL_MODEL_PATH": LOCAL_MODEL_PATH,
        "LOCAL_ADAPTER_PATH": LOCAL_ADAPTER_PATH,
        "LOCAL_THREADS": LOCAL_THREADS,
        "LOCAL_MAX_NEW_TOKENS": LOCAL_MAX_NEW_TOKENS,
        "MYSQL_HOST": MYSQL_HOST,
        "MYSQL_PORT": MYSQL_PORT,
        "MYSQL_USER": MYSQL_USER,
        "MYSQL_PASSWORD": MYSQL_PASSWORD,
        "MYSQL_DATABASE": MYSQL_DATABASE,
    }
    for key, value in config.items():
        if value:
            os.environ[key] = value


if __name__ == "__main__":
    apply_config()
    arguments = ["app.py"] + (["--question", QUESTION] if QUESTION else [])
    if AUTO_CHART:
        arguments.extend(["--auto-chart", "--chart-output-dir", CHART_OUTPUT_DIR])
    if AUTO_CHART and OPEN_CHART:
        arguments.append("--open-chart")
    sys.argv = arguments
    main()
