import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def load_env_file():
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    mode: str
    api_base: str
    api_key: str
    model: str
    ca_bundle: str
    local_model_path: str
    local_adapter_path: str
    local_threads: int
    local_max_new_tokens: int
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str


def get_settings():
    load_env_file()
    return Settings(
        mode=os.getenv("LLM_MODE", "api").lower(),
        api_base=os.getenv("LLM_API_BASE", "https://api.deepseek.com/v1").rstrip("/"),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        ca_bundle=os.getenv("LLM_CA_BUNDLE", ""),
        local_model_path=os.getenv("LOCAL_MODEL_PATH", ""),
        local_adapter_path=os.getenv("LOCAL_ADAPTER_PATH", ""),
        local_threads=int(os.getenv("LOCAL_THREADS", "8")),
        local_max_new_tokens=int(os.getenv("LOCAL_MAX_NEW_TOKENS", "256")),
        mysql_host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        mysql_port=int(os.getenv("MYSQL_PORT", "3306")),
        mysql_user=os.getenv("MYSQL_USER", "root"),
        mysql_password=os.getenv("MYSQL_PASSWORD", ""),
        mysql_database=os.getenv("MYSQL_DATABASE", "ecommerce_text_to_sql"),
    )
