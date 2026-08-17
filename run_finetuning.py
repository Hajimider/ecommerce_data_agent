"""本机 IDE 一键运行入口。修改本页顶部配置后直接运行。"""

import os
import subprocess
import sys
from pathlib import Path


# 操作：generate、prepare_public、train、evaluate、evaluate_public、compare_epochs、all；apply_reviews 仅用于可选人工覆盖。
# compare_epochs 会依次训练并评估固定 72/24 数据上的 epoch 1、2、3，请预留足够时间。
ACTION = "compare_epochs"

# True：调用 API 教师和 API 裁判；False：只使用 15 条人工种子做链路检查。
USE_API_TEACHER = True

# 本地基础模型目录。留空时读取 .env 中的 LOCAL_MODEL_PATH。
MODEL_PATH = ""
ADAPTER_OUTPUT = "outputs/student_lora_cspider_epoch2"
# 评估报告保存位置；每次实验建议使用不同文件名，避免覆盖历史结果。
EVALUATION_OUTPUT = "outputs/evaluation_cspider_domain_epoch2.json"
EPOCHS = 2
MAX_LENGTH = 512  # 单条训练序列上限；超长表结构会裁剪中间部分并完整保留问题和标准 SQL。
MAX_SAMPLES = 0  # 0 表示使用全部数据。
VARIANTS_PER_SEED = 4
JUDGE_MIN_CONFIDENCE = 0.95
INCLUDE_API_IN_EVALUATION = False

# True：训练时使用“CSpider 公开子集 + 电商领域数据”的固定快照；False：只使用电商数据。
USE_CSPIDER = True
# CSpider 原始目录应包含 train.json、dev.json、tables.json 和 database/。
CSPIDER_SOURCE_DIR = "data/public/cspider/raw"
CSPIDER_PUBLIC_TRAIN_SAMPLES = 200  # 0 表示使用全部训练样本；CPU 初学实验建议先用 200。
CSPIDER_PUBLIC_DEV_SAMPLES = 50     # 0 表示使用全部 dev；公开评测会分别调用 Base 和 LoRA。
CSPIDER_RANDOM_SEED = 42
DOMAIN_TRAIN_DATA = "data/distillation/verified_train.jsonl"
COMBINED_TRAIN_DATA = "data/training/cspider_ecommerce_train.jsonl"
CSPIDER_DEV_DATA = "data/evaluation/cspider_dev.jsonl"
CSPIDER_EVALUATION_OUTPUT = "outputs/evaluation_cspider_epoch2.json"

# 严格 epoch 对比：训练集、测试集和其他训练参数保持不变，只改变 epoch。
FIXED_TRAIN_DATA = "data/distillation/fixed_train_72.jsonl"
FIXED_TEST_DATA = "data/evaluation/test.jsonl"
FIXED_TRAIN_SAMPLES = 72
FIXED_TEST_SAMPLES = 24
COMPARISON_EPOCHS = (1, 2, 3)

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
    run("scripts/prepare_evaluation_data.py", "--train-path", DOMAIN_TRAIN_DATA)


def apply_reviews():
    run("scripts/generate_distillation_data.py", "--apply-reviews")


def prepare_public_data():
    run(
        "scripts/prepare_cspider.py",
        "--source-dir", CSPIDER_SOURCE_DIR,
        "--domain-path", DOMAIN_TRAIN_DATA,
        "--combined-output", COMBINED_TRAIN_DATA,
        "--dev-output", CSPIDER_DEV_DATA,
        "--public-train-samples", str(CSPIDER_PUBLIC_TRAIN_SAMPLES),
        "--public-dev-samples", str(CSPIDER_PUBLIC_DEV_SAMPLES),
        "--seed", str(CSPIDER_RANDOM_SEED),
    )


def train_model(data_path=None, output_dir=None, epochs=None, max_samples=None):
    model_path = configured_model_path()
    if not model_path:
        raise SystemExit("请先填写 MODEL_PATH，或在 .env 中配置 LOCAL_MODEL_PATH。")
    data_path = data_path or (COMBINED_TRAIN_DATA if USE_CSPIDER else DOMAIN_TRAIN_DATA)
    output_dir = output_dir or ADAPTER_OUTPUT
    epochs = epochs or EPOCHS
    command = [
        "scripts/train_student.py", "--model-path", model_path,
        "--data-path", data_path,
        "--output-dir", output_dir,
        "--epochs", str(epochs),
        "--max-length", str(MAX_LENGTH),
    ]
    max_samples = MAX_SAMPLES if max_samples is None else max_samples
    if max_samples:
        command.extend(["--max-samples", str(max_samples)])
    run(*command)


def evaluate_model(adapter_path=None, report_path=None, test_path="data/evaluation/test.jsonl", include_api=None, max_samples=None):
    model_path = configured_model_path()
    if not model_path:
        raise SystemExit("请先填写 MODEL_PATH，或在 .env 中配置 LOCAL_MODEL_PATH。")
    adapter_path = adapter_path or ADAPTER_OUTPUT
    report_path = report_path or EVALUATION_OUTPUT
    include_api = INCLUDE_API_IN_EVALUATION if include_api is None else include_api
    command = [
        "scripts/evaluate_finetuning.py",
        "--model-path", model_path,
        "--adapter-path", adapter_path,
        "--test-path", test_path,
        "--report-path", report_path,
    ]
    max_samples = MAX_SAMPLES if max_samples is None else max_samples
    if max_samples:
        command.extend(["--max-samples", str(max_samples)])
    if include_api:
        command.append("--include-api")
    run(*command)


def count_jsonl(path):
    with (ROOT / path).open("r", encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def compare_epochs():
    run("scripts/prepare_evaluation_data.py", "--check-only", "--output-path", FIXED_TEST_DATA, "--train-path", FIXED_TRAIN_DATA)
    actual_train = count_jsonl(FIXED_TRAIN_DATA)
    actual_test = count_jsonl(FIXED_TEST_DATA)
    if actual_train != FIXED_TRAIN_SAMPLES or actual_test != FIXED_TEST_SAMPLES:
        raise SystemExit(
            f"固定实验数据数量错误：训练集 {actual_train}/{FIXED_TRAIN_SAMPLES}，"
            f"测试集 {actual_test}/{FIXED_TEST_SAMPLES}。"
        )

    outputs = [
        (ROOT / f"outputs/student_lora_fixed_epoch{epoch}", ROOT / f"outputs/evaluation_fixed_epoch{epoch}.json")
        for epoch in COMPARISON_EPOCHS
    ]
    existing = [str(path.relative_to(ROOT)) for pair in outputs for path in pair if path.exists()]
    if existing:
        raise SystemExit(f"固定实验不会覆盖已有产物，请先改名或移走：{', '.join(existing)}")

    for epoch, (adapter_full_path, report_full_path) in zip(COMPARISON_EPOCHS, outputs):
        adapter_path = str(adapter_full_path.relative_to(ROOT))
        report_path = str(report_full_path.relative_to(ROOT))
        train_model(FIXED_TRAIN_DATA, adapter_path, epoch, max_samples=0)
        evaluate_model(adapter_path, report_path, FIXED_TEST_DATA, include_api=False, max_samples=0)


def evaluate_public_model():
    if not USE_CSPIDER:
        raise SystemExit("evaluate_public 需要先把 USE_CSPIDER 设为 True。")
    model_path = configured_model_path()
    if not model_path:
        raise SystemExit("请先填写 MODEL_PATH，或在 .env 中配置 LOCAL_MODEL_PATH。")
    run(
        "scripts/evaluate_cspider.py",
        "--model-path", model_path,
        "--adapter-path", ADAPTER_OUTPUT,
        "--test-path", CSPIDER_DEV_DATA,
        "--source-dir", CSPIDER_SOURCE_DIR,
        "--report-path", CSPIDER_EVALUATION_OUTPUT,
    )


def main():
    apply_overrides()
    if ACTION not in {"generate", "prepare_public", "apply_reviews", "train", "evaluate", "evaluate_public", "compare_epochs", "all"}:
        raise SystemExit("ACTION 只能是 generate、prepare_public、apply_reviews、train、evaluate、evaluate_public、compare_epochs 或 all。")
    if ACTION in {"generate", "all"}:
        generate_data()
    if ACTION == "prepare_public" or (ACTION == "all" and USE_CSPIDER):
        prepare_public_data()
    if ACTION == "apply_reviews":
        apply_reviews()
    if ACTION in {"train", "all"}:
        train_model()
    if ACTION in {"evaluate", "all"}:
        evaluate_model()
    if ACTION == "evaluate_public" or (ACTION == "all" and USE_CSPIDER):
        evaluate_public_model()
    if ACTION == "compare_epochs":
        compare_epochs()


if __name__ == "__main__":
    main()
