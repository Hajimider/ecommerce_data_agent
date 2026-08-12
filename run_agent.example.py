"""复制为 run_agent.py 后，在 IDE 中一键运行。"""

import os
import sys

from app import main


LLM_MODE = "api"  # api 调用云端模型；local 加载本地模型
LLM_API_BASE = "https://api.deepseek.com/v1"  # API 兼容接口地址
LLM_API_KEY = "请填写你的API密钥"  # 真实密钥仅保留在本机
LLM_MODEL = "deepseek-chat"  # 服务商提供的模型名称
LLM_CA_BUNDLE = ""  # 自签名网络证书的 PEM 路径；普通网络留空

LOCAL_MODEL_PATH = "path/to/Qwen2.5-1.5B-Instruct"  # 仅 local 模式使用
LOCAL_ADAPTER_PATH = ""  # 可选 LoRA 适配器目录；留空使用基础模型
LOCAL_THREADS = "8"  # CPU 推理线程数
LOCAL_MAX_NEW_TOKENS = "256"  # 单次最多生成 token 数

MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = "3306"
MYSQL_USER = "root"
MYSQL_PASSWORD = "请填写你的MySQL密码"
MYSQL_DATABASE = "ecommerce_text_to_sql"

QUESTION = "统计各商品分类的销售额并按销售额降序排列"  # 留空进入连续提问模式


if __name__ == "__main__":
    for key, value in {
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
    }.items():
        if value:
            os.environ[key] = value
    sys.argv = ["app.py"] + (["--question", QUESTION] if QUESTION else [])
    main()
