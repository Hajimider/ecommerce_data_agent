import json
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMClient:
    def __init__(self, settings):
        if not settings.api_key:
            raise ValueError("未配置 LLM_API_KEY。请先在 .env 中填写 API Key。")
        self.base_url = settings.api_base
        self.api_key = settings.api_key
        self.model = settings.model
        self.ssl_context = self._ssl_context(settings.ca_bundle)

    @staticmethod
    def _ssl_context(ca_bundle):
        if ca_bundle:
            return ssl.create_default_context(cafile=ca_bundle)
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except ImportError:
            return ssl.create_default_context()

    def chat(self, system, user, temperature=0):
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=60, context=self.ssl_context) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API 请求失败（HTTP {exc.code}）：{detail}") from exc
        except URLError as exc:
            reason = str(exc.reason)
            if "CERTIFICATE_VERIFY_FAILED" in reason:
                raise RuntimeError(
                    "API 证书校验失败。请先在当前 Python 环境运行 python -m pip install -r requirements.txt；"
                    "若仍失败，请在 run_agent.py 中填写 LLM_CA_BUNDLE 为网络根证书 PEM 文件路径。"
                ) from exc
            raise RuntimeError(f"无法连接 API：{exc.reason}") from exc
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise RuntimeError(f"API 返回格式无法识别：{data}") from exc


class LocalLLMClient:
    """按需加载本地聊天模型，避免 API 模式导入模型依赖。"""

    def __init__(self, settings):
        if not settings.local_model_path:
            raise ValueError("本地模式需要在 run_agent.py 中填写 LOCAL_MODEL_PATH。")
        self.settings = settings
        self.model = None
        self.tokenizer = None

    def _load(self):
        if self.model is not None:
            return
        model_path = Path(self.settings.local_model_path)
        if not model_path.is_dir():
            raise ValueError(f"LOCAL_MODEL_PATH 不是有效模型目录：{model_path}")
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError("本地模式缺少 torch 或 transformers，请安装 requirements.txt 中的本地模型依赖。") from exc
        torch.set_num_threads(max(1, self.settings.local_threads))
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            dtype=torch.float32,
            low_cpu_mem_usage=True,
            local_files_only=True,
        )
        if self.settings.local_adapter_path:
            adapter_path = Path(self.settings.local_adapter_path)
            if not adapter_path.is_dir():
                raise ValueError(f"LOCAL_ADAPTER_PATH 不是有效适配器目录：{adapter_path}")
            try:
                from peft import PeftModel
            except ImportError as exc:
                raise RuntimeError("加载 LoRA 适配器需要 peft，请安装本地模型依赖。") from exc
            self.model = PeftModel.from_pretrained(self.model, adapter_path, is_trainable=False)
        self.model.eval()

    def chat(self, system, user, temperature=0):
        del temperature
        self._load()
        import torch

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt")
        end_id = self.tokenizer.convert_tokens_to_ids("<|im_end|>")
        eos_token_id = [self.tokenizer.eos_token_id, end_id] if end_id not in (self.tokenizer.eos_token_id, self.tokenizer.unk_token_id) else self.tokenizer.eos_token_id
        with torch.inference_mode():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=self.settings.local_max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=eos_token_id,
            )
        answer_ids = output_ids[0, inputs["input_ids"].shape[1] :]
        return self.tokenizer.decode(answer_ids, skip_special_tokens=True).strip()


def create_llm_client(settings):
    if settings.mode == "api":
        return LLMClient(settings)
    if settings.mode == "local":
        return LocalLLMClient(settings)
    raise ValueError("LLM_MODE 只能是 api 或 local。")
