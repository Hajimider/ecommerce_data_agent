"""本机 IDE 一键运行入口。修改本页顶部配置后直接运行。"""

import os
import subprocess
import sys
from pathlib import Path


# 操作：generate（生成并自动审核）、train、evaluate、all；apply_reviews 仅用于可选人工覆盖。
ACTION = "generate"

# True：调用 API 教师和 API 裁判；False：只使用 15 条人工种子做链路检查。
USE_API_TEACHER = True

# 本地基础模型目录。留空时读取 .env 中的 LOCAL_MODEL_PATH。
MODEL_PATH = ""
ADAPTER_OUTPUT = "outputs/student_lora"
# 评估报告保存位置；每次实验建议使用不同文件名，避免覆盖历史结果。
EVALUATION_OUTPUT = "outputs/evaluation.json"
EPOCHS = 2
MAX_SAMPLES = 0  # 0 表示使用全部数据。
VARIANTS_PER_SEED = 4
JUDGE_MIN_CONFIDENCE = 0.95
INCLUDE_API_IN_EVALUATION = False

# 留空表示继续使用 .env；填写后只覆盖本次运行，不会写回文件。
LLM_API_BASE = ""
LLM_API_KEY = ""
LLM_MODEL = ""
# 裁判配置必须全部填写或全部留空；留空时复用教师 API。
JUDGE_API_BASE = ""
JUDGE_API_KEY = ""
JUDGE_MODEL = ""
MYSQL_HOST = ""
MYSQL_PORT = ""
MYSQL_USER = ""
MYSQL_PASSWORD = ""
MYSQL_DATABASE = ""


ROOT = Path(__file__).resolve().parent


def apply_overrides():
    values = {
        "LLM_API_BASE": LLM_API_BASE,
        "LLM_API_KEY": LLM_API_KEY,
        "LLM_MODEL": LLM_MODEL,
        "JUDGE_API_BASE": JUDGE_API_BASE,
        "JUDGE_API_KEY": JUDGE_API_KEY,
        "JUDGE_MODEL": JUDGE_MODEL,
        "JUDGE_MIN_CONFIDENCE": JUDGE_MIN_CONFIDENCE,
        "MYSQL_HOST": MYSQL_HOST,
        "MYSQL_PORT": MYSQL_PORT,
        "MYSQL_USER": MYSQL_USER,
        "MYSQL_PASSWORD": MYSQL_PASSWORD,
        "MYSQL_DATABASE": MYSQL_DATABASE,
    }
    for key, value in values.items():
        if value:
            os.environ[key] = str(value)


def run(*arguments):
    print(f"\n> python {' '.join(arguments)}")
    subprocess.run([sys.executable, *arguments], cwd=ROOT, check=True)


def configured_model_path():
    if MODEL_PATH:
        return MODEL_PATH
    from config import get_settings

    return get_settings().local_model_path


def generate_data():
    command = ["scripts/generate_distillation_data.py", "--variants", str(VARIANTS_PER_SEED), "--judge-min-confidence", str(JUDGE_MIN_CONFIDENCE)]
    if not USE_API_TEACHER:
        command.append("--seed-only")
    run(*command)
    run("scripts/prepare_evaluation_data.py")


def apply_reviews():
    run("scripts/generate_distillation_data.py", "--apply-reviews")


def train_model():
    model_path = configured_model_path()
    if not model_path:
        raise SystemExit("请先填写 MODEL_PATH，或在 .env 中配置 LOCAL_MODEL_PATH。")
    command = ["scripts/train_student.py", "--model-path", model_path, "--output-dir", ADAPTER_OUTPUT, "--epochs", str(EPOCHS)]
    if MAX_SAMPLES:
        command.extend(["--max-samples", str(MAX_SAMPLES)])
    run(*command)


def evaluate_model():
    model_path = configured_model_path()
    if not model_path:
        raise SystemExit("请先填写 MODEL_PATH，或在 .env 中配置 LOCAL_MODEL_PATH。")
    command = [
        "scripts/evaluate_finetuning.py",
        "--model-path", model_path,
        "--adapter-path", ADAPTER_OUTPUT,
        "--report-path", EVALUATION_OUTPUT,
    ]
    if MAX_SAMPLES:
        command.extend(["--max-samples", str(MAX_SAMPLES)])
    if INCLUDE_API_IN_EVALUATION:
        command.append("--include-api")
    run(*command)


def main():
    apply_overrides()
    if ACTION not in {"generate", "apply_reviews", "train", "evaluate", "all"}:
        raise SystemExit("ACTION 只能是 generate、apply_reviews、train、evaluate 或 all。")
    if ACTION in {"generate", "all"}:
        generate_data()
    if ACTION == "apply_reviews":
        apply_reviews()
    if ACTION in {"train", "all"}:
        train_model()
    if ACTION in {"evaluate", "all"}:
        evaluate_model()


if __name__ == "__main__":
    main()
