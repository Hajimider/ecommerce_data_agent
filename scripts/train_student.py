import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import normalize_select
from scripts.distillation_data import read_jsonl


LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def parse_args():
    parser = argparse.ArgumentParser(description="在 CPU 上训练电商 Text-to-SQL LoRA 学生模型")
    parser.add_argument("--model-path", default="", help="本地 Qwen 基础模型目录")
    parser.add_argument("--data-path", default="data/distillation/verified_train.jsonl")
    parser.add_argument("--output-dir", default="outputs/student_lora")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--gradient-accumulation", type=int, default=4)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--check-data", action="store_true", help="只检查训练数据，不加载模型")
    return parser.parse_args()


def validate_records(path):
    records = read_jsonl(path)
    if not records:
        raise ValueError("训练数据为空")
    questions = set()
    for line_number, record in enumerate(records, start=1):
        question = record.get("question")
        sql = record.get("sql")
        messages = record.get("messages")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"第 {line_number} 行缺少 question")
        normalize_select(sql)
        question_key = (record.get("db_id", "ecommerce_text_to_sql"), question.strip())
        if question_key in questions:
            raise ValueError(f"第 {line_number} 行同一数据库内问题重复：{question}")
        questions.add(question_key)
        if not isinstance(messages, list) or [item.get("role") for item in messages] != ["system", "user", "assistant"]:
            raise ValueError(f"第 {line_number} 行 messages 必须依次包含 system、user、assistant")
        try:
            answer = json.loads(messages[-1]["content"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"第 {line_number} 行 assistant 不是合法 JSON") from exc
        if normalize_select(answer.get("sql")) != normalize_select(sql):
            raise ValueError(f"第 {line_number} 行 assistant SQL 与 sql 字段不一致")
    return records


def token_ids(tokenizer, messages, add_generation_prompt):
    encoded = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=add_generation_prompt)
    return encoded["input_ids"] if hasattr(encoded, "keys") else encoded


def encode_record(tokenizer, record, max_length):
    prompt_messages = record["messages"][:2]
    prompt_ids = token_ids(tokenizer, prompt_messages, True)
    full_ids = token_ids(tokenizer, record["messages"], False)
    if full_ids[: len(prompt_ids)] != prompt_ids:
        raise ValueError("聊天模板的 prompt 与完整对话前缀不一致")

    answer_ids = full_ids[len(prompt_ids) :]
    if not answer_ids:
        raise ValueError("聊天模板没有保留 assistant 回答")
    if len(answer_ids) >= max_length:
        raise ValueError("max-length 太小，无法保留完整 assistant 回答")

    prompt_budget = max_length - len(answer_ids)
    prompt_truncated = len(prompt_ids) > prompt_budget
    if prompt_truncated:
        # 保留系统指令和用户问题，优先裁剪位于中间的超长数据库结构。
        head_size = min(128, prompt_budget // 2)
        tail_size = prompt_budget - head_size
        prompt_ids = prompt_ids[:head_size] + prompt_ids[-tail_size:]

    input_ids = prompt_ids + answer_ids
    labels = [-100] * len(prompt_ids) + answer_ids
    return {
        "input_ids": input_ids,
        "attention_mask": [1] * len(input_ids),
        "labels": labels,
        "prompt_truncated": prompt_truncated,
    }


def train(args, records):
    output_dir = Path(args.output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"输出目录不是空目录：{output_dir}。请改用新的 --output-dir，项目不会覆盖已有适配器。")

    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from torch.optim import AdamW
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_path = Path(args.model_path)
    if not model_path.is_dir():
        raise ValueError("--model-path 不是有效的本地模型目录")
    if args.epochs < 1 or args.max_length < 128 or args.gradient_accumulation < 1:
        raise ValueError("epochs、max-length 和 gradient-accumulation 参数不合理")
    if args.max_samples:
        records = records[: args.max_samples]
    random.seed(42)
    torch.manual_seed(42)
    torch.set_num_threads(max(1, args.threads))

    print("1/5 加载 tokenizer 并处理训练数据...")
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    encoded_records = [encode_record(tokenizer, record, args.max_length) for record in records]
    truncated_count = sum(item.pop("prompt_truncated") for item in encoded_records)
    if truncated_count:
        print(f"超长提示已安全裁剪：{truncated_count} 条；assistant 标准 SQL 均完整保留。")

    class TrainingDataset(Dataset):
        def __len__(self):
            return len(encoded_records)

        def __getitem__(self, index):
            return encoded_records[index]

    def collate_batch(batch):
        max_size = max(len(item["input_ids"]) for item in batch)
        input_ids = torch.full((len(batch), max_size), tokenizer.pad_token_id, dtype=torch.long)
        attention_mask = torch.zeros((len(batch), max_size), dtype=torch.long)
        labels = torch.full((len(batch), max_size), -100, dtype=torch.long)
        for index, item in enumerate(batch):
            size = len(item["input_ids"])
            input_ids[index, :size] = torch.tensor(item["input_ids"], dtype=torch.long)
            attention_mask[index, :size] = 1
            labels[index, :size] = torch.tensor(item["labels"], dtype=torch.long)
        return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}

    loader = DataLoader(TrainingDataset(), batch_size=1, shuffle=True, collate_fn=collate_batch)
    print("2/5 以 float32 将基础模型加载到 CPU...")
    model = AutoModelForCausalLM.from_pretrained(model_path, dtype=torch.float32, low_cpu_mem_usage=True, local_files_only=True)
    model.config.use_cache = False
    print("3/5 注入 LoRA 适配器...")
    model = get_peft_model(model, LoraConfig(task_type=TaskType.CAUSAL_LM, r=8, lora_alpha=16, lora_dropout=0.05, target_modules=LORA_TARGETS, bias="none"))
    model.print_trainable_parameters()
    optimizer = AdamW((parameter for parameter in model.parameters() if parameter.requires_grad), lr=args.learning_rate)

    print("4/5 开始训练...")
    model.train()
    optimizer.zero_grad(set_to_none=True)
    updates = 0
    final_loss = None
    for epoch in range(args.epochs):
        loss_sum = 0.0
        for step, batch in enumerate(loader):
            group_start = (step // args.gradient_accumulation) * args.gradient_accumulation
            group_size = min(args.gradient_accumulation, len(loader) - group_start)
            loss = model(**batch).loss
            (loss / group_size).backward()
            loss_sum += loss.item()
            if (step + 1) % args.gradient_accumulation == 0 or step + 1 == len(loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                updates += 1
            if (step + 1) % 20 == 0 or step + 1 == len(loader):
                final_loss = loss_sum / (step + 1)
                print(f"epoch={epoch + 1}/{args.epochs} sample={step + 1}/{len(loader)} avg_loss={final_loss:.4f}")

    print("5/5 保存 LoRA 适配器...")
    output_dir.mkdir(parents=True, exist_ok=True)
    for config in model.peft_config.values():
        config.base_model_name_or_path = model_path.name
    model.base_model.name_or_path = model_path.name
    model.get_base_model().config._name_or_path = model_path.name
    model.save_pretrained(output_dir, save_embedding_layers=False)
    tokenizer.save_pretrained(output_dir)
    summary = {
        "samples": len(records),
        "data_file": Path(args.data_path).name,
        "data_sha256": hashlib.sha256(Path(args.data_path).read_bytes()).hexdigest(),
        "source_counts": dict(Counter(record.get("source", "unknown") for record in records)),
        "truncated_prompts": truncated_count,
        "epochs": args.epochs,
        "max_length": args.max_length,
        "gradient_accumulation": args.gradient_accumulation,
        "optimizer_updates": updates,
        "final_average_loss": final_loss,
    }
    (output_dir / "training_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"训练完成，适配器已保存到：{output_dir}")


def main():
    args = parse_args()
    try:
        records = validate_records(args.data_path)
        print(f"数据检查通过，共 {len(records)} 条样本")
        if not args.check_data:
            if not args.model_path:
                raise ValueError("训练时必须提供 --model-path")
            train(args, records)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"错误：{exc}") from exc


if __name__ == "__main__":
    main()
