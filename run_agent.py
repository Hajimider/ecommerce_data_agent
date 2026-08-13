"""IDE 一键启动入口。

在本文件开头修改配置后，直接右键运行本文件即可。
敏感配置留空时读取项目根目录的 .env 文件。
"""

import os
import sys

from app import main


# 运行方式：api 调用云端模型；local 加载本地模型。二选一。
LLM_MODE = ""

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
QUESTION = "查询张伟的全部订单，按下单日期排序"


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
    sys.argv = ["app.py"] + (["--question", QUESTION] if QUESTION else [])
    main()
