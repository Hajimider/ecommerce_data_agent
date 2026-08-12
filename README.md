# Ecommerce-Data-Agent

## 项目说明

这是一个以本地 Qwen LoRA 微调和黑盒知识蒸馏为主线的中文 Text-to-SQL 项目。强 API 模型充当教师，只生成标准问题的语义等价改写；API 裁判批量检查语义一致性，候选样本通过格式、安全、去重、置信度和 MySQL 执行校验后训练本地学生模型。最后在独立人工测试集上比较本地基础模型、LoRA 学生模型和 API 教师模型，并把 LoRA 学生接入电商数据分析 Agent 做落地演示。

项目重点是完整走通“教师数据生成 → LoRA 训练 → 同模型微调前后评估 → Agent 应用”的微调全过程。Agent 不是主项目本身，而是展示微调模型如何进入真实链路：业务知识检索、SQL 规划、安全检查、数据库执行、一次错误修复和结果解释。

项目提供两种启动方式：

- `run_agent.py`：适合 IDE 一键运行，模型、API、MySQL 和测试问题集中配置。
- `run_finetuning.py`：适合 IDE 一键生成数据、训练和评估，参数集中配置。
- `app.py`：适合命令行单题测试、连续提问和无模型自检。

项目使用固定教学数据库，只允许单条 `SELECT` 查询，不应连接生产数据库或处理真实敏感业务数据。

## 实际问题与解决思路

| 实际问题 | 项目处理方式 | 可检查的输出 |
| --- | --- | --- |
| 用户问题没有 SQL 结构 | 检索表结构和指标口径，将问题与上下文交给模型规划 | 检索到的知识标题、模型生成 SQL |
| 模型可能编造字段或关联关系 | 知识库明确外键路径和指标口径；SQL 失败时携带数据库错误修复一次 | 首次 SQL、重试状态、最终 SQL |
| 大模型可能生成写操作或多条语句 | 执行前拒绝非 `SELECT`、危险关键字、注释和多语句 | 明确的安全校验错误 |
| SQL 能执行但不方便阅读 | 执行使用规范化原始 SQL，终端使用多行缩进格式展示 | 美化后的 SQL |
| API 不可用或不希望上传数据 | `LLM_MODE` 可切换 API 与本地 Qwen，本地模式不发送问题和结果到云端 | 当前模型配置和本地加载日志 |
| 小模型能力不足但本机无法训练大模型 | 强 API 模型只改写人工标准问题，沿用已验证 SQL 标签训练本地学生模型 | 合成 JSONL、过滤统计和三方评测报告；当前项目主线 |

项目输出用于学习和算法工程展示，不构成真实经营决策建议。

## 数据集

项目不下载外部数据集，复用固定的 `ecommerce_text_to_sql` MySQL 教学库。数据库由 Text-to-SQL 项目的初始化脚本创建。

| 数据内容 | 数量 | 主要字段 |
| --- | ---: | --- |
| 用户 `users` | 8 | 用户名、城市、注册日期、会员等级 |
| 商品 `products` | 8 | 商品名、分类、价格、库存 |
| 订单 `orders` | 12 | 用户、日期、状态、订单金额 |
| 订单明细 `order_items` | 17 | 订单、商品、数量、成交单价 |
| 业务知识条目 | 4 | 表关系、销售指标、订单用户、库存商品 |

业务知识直接保存在 `knowledge.py`，用于轻量关键词检索。销售额统一定义为 `SUM(quantity * unit_price)`，销量统一定义为 `SUM(quantity)`。订单和商品不能直接关联，必须经过 `order_items`。

项目内置 15 条人工标准任务和 12 条独立人工测试题。启用 API 教师后，每个种子可生成多个问法，只有 API 裁判判定完全等价且置信度达到阈值的改写才进入 `verified_train.jsonl`。测试题不发送给教师或裁判 API，也不参与训练或提示调优。

## 数据链路

```text
中文分析问题
  -> 关键词检索表结构、外键关系和指标口径
  -> API 或本地 Qwen 返回 {"sql": "SELECT ...;"}
  -> 拒绝写操作、注释和多语句
  -> MySQL 执行，最多返回 100 行
  -> 首次失败时携带错误信息修复一次
  -> API 或本地 Qwen 读取查询结果并生成中文结论
  -> 终端展示知识来源、格式化 SQL、结果表格和重试状态
```

合成数据与知识蒸馏链路：

```text
固定数据库、业务规则和问题模板
  -> 强 API 教师模型只生成自然问题改写，沿用人工标准 SQL
  -> JSON 格式检查、SQL 安全检查和 MySQL 执行校验
  -> API 裁判批量审核、置信度过滤和问题去重
  -> 保存合成训练集 / 独立人工测试集
  -> 本地 Qwen 基础模型训练 LoRA 学生模型
  -> 比较本地基础模型、LoRA 学生模型和 API 教师模型
```

## 方法与训练

### 检索链路

1. 根据用户问题中的“销售额”“订单”“城市”“库存”等词项计算知识条目命中分数。
2. 选取分数最高的最多 3 条业务知识；没有命中时返回基础表结构。
3. 将知识内容和用户问题一起传给模型，不让模型依赖记忆猜测字段。
4. 该检索器适合固定教学库；扩展到企业文档时应替换为向量检索和版本化知识库。

### 安全校验与错误修复

生成结果先解析为 JSON，再提取 `sql` 字段。数据库工具只接受单条 `SELECT`，拒绝 `INSERT`、`UPDATE`、`DELETE`、`DROP`、注释和多语句。结果最多读取 100 行，防止终端一次输出过多内容。

SQL 首次执行失败时，Agent 将数据库错误和原问题交给同一模型修复一次。第二次仍失败就停止，不会无限循环。当前校验是字符串级防线，不能替代数据库只读账号、最小权限和查询超时。

### 模型生成

API 模式通过 OpenAI-compatible `/chat/completions` 接口调用云端模型。本地模式使用 Transformers 加载本地聊天模型，可通过 `LOCAL_ADAPTER_PATH` 挂载 PEFT LoRA 适配器。两种后端实现相同的 `chat(system, user)` 接口，Agent 编排层不关心具体模型来源。

严格来说，让 API 生成问题改写叫“合成数据”；把经过自动质量过滤的数据用于训练本地学生模型，属于数据驱动的知识蒸馏，也常称黑盒蒸馏。名称并不代表数据天然可靠，语义偏离的改写同样会被学生模型学到，因此裁判不确定或返回异常时直接丢弃。

项目已经完成合成数据生成、批量 API 裁判、LoRA 训练和自动评估。训练目标与 Agent 完全一致：输入同一套 `SQL_SYSTEM`、检索上下文和用户问题，只对 assistant 的 `{"sql":"SELECT ...;"}` 回答计算损失。本次实验的实际指标以各个 `outputs/evaluation_*.json` 报告为准，并重点比较同一基础模型加载 LoRA 前后的执行结果正确率。

## 运行结果

下面分为工程验证和一次已经完成的模型评估结果。评估使用与训练隔离的 12 条人工测试题；“执行结果正确率”按查询结果与标准 SQL 结果完全一致计算。

### API 模式

| 验证项 | 结果 |
| --- | --- |
| OpenAI-compatible 请求格式 | 已实现 |
| API 根地址与完整 `/chat/completions` 地址兼容 | 已实现 |
| Windows 证书库与自定义 CA | 已实现 |
| API 改写批量裁判和置信度过滤 | 已实现，默认阈值 0.95 |
| 本次候选样本自动审核 | 共 63 条，通过 54 条，拒绝 9 条 |
| epoch2 API 教师重复评估 | 已完成 2 次，指标一致，报告位于 `outputs/evaluation_epoch2_api_run1.json` 和 `outputs/evaluation_epoch2_api_run2.json` |

### 本地模式

| 验证项 | 结果 |
| --- | --- |
| 本地 Qwen 权重加载 | 通过 |
| 最小文本生成 | 通过 |
| 可选 PEFT LoRA 加载 | 通过，已用于本次评估 |
| MySQL 教学库连接和只读查询 | 通过 |
| `app.py --self-test` | 通过 |

本地最小生成验证只能证明模型能够加载和回答；本次独立测试集评估进一步给出了 Text-to-SQL 执行结果正确率、SQL 可执行率和 Agent 重试率。

### 微调链路

| 验证项 | 结果 |
| --- | --- |
| 15 条人工标准 SQL 的 MySQL 执行校验 | 通过 |
| 12 条独立测试 SQL 的 MySQL 执行校验 | 通过 |
| API 教师生成与裁判自动审核 | 通过，63 条候选中 54 条进入训练集 |
| epoch1 LoRA 训练 | 已完成，54 条样本、1 轮、14 次优化器更新，最终平均损失 0.0907 |
| epoch2 LoRA 训练 | 已完成，71 条样本、2 轮、36 次优化器更新，最终平均损失 0.00385 |
| epoch3 LoRA 训练 | 已完成，72 条样本、3 轮、54 次优化器更新，最终平均损失 0.00041 |
| 基础模型、LoRA 与 API 教师评估代码 | 已实现并运行 |
| 各轮本地评估报告 | 已完成，报告位于 `outputs/evaluation_epoch1.json`、`outputs/evaluation_epoch2.json` 和 `outputs/evaluation_epoch3.json` |

### 独立测试集评估结果

本次评估共 12 条测试题，基础模型和 LoRA 模型使用同一套提示模板、同一数据库和同一测试集。各轮结果如下：

| 评估报告 | 训练样本数 | LoRA 轮数 | 执行结果正确率 | SQL 可执行率 | Agent 首次成功率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `evaluation_epoch1.json` | 54 | 1 | 58.33% | 91.67% | 75.00% |
| `evaluation_epoch2.json` | 71 | 2 | 75.00% | 91.67% | 91.67% |
| `evaluation_epoch3.json` | 72 | 3 | 66.67% | 83.33% | 83.33% |

每份报告中的本地基础模型基线均为：执行结果正确率 33.33%、SQL 可执行率 91.67%、Agent 首次成功率 83.33%。

结论：本次已运行的结果中，epoch2 的执行结果正确率最高，为 75.00%；epoch3 下降到 66.67%，说明继续增加训练轮数并不一定提升效果。三个实验使用了相同的候选集、训练集和测试集文件路径，测试集内容保持一致；但由于训练前不同时间点曾重新生成过候选/训练文件，三个适配器实际读取到的训练样本快照分别记录为 54、71、72 条。因此这组结果可以比较三次完整实验，但不能严格把差异全部归因于 `EPOCHS`。如果要做严谨的 epoch 单变量实验，应先固定 `verified_train.jsonl` 快照，再训练各轮。

### epoch2 三方评估

epoch2 的 API 对照评估连续运行 2 次，结果一致：

| 指标 | 本地基础模型 | LoRA 学生模型 | API 教师模型 |
| --- | ---: | ---: | ---: |
| JSON/SQL 提取率 | 100.00% | 100.00% | 100.00% |
| SQL 可执行率 | 91.67% | 91.67% | 100.00% |
| 执行结果正确率 | 33.33% | 75.00% | 50.00% |
| Agent 首次成功率 | 83.33% | 91.67% | 100.00% |
| Agent 重试率 | 16.67% | 8.33% | 0.00% |

API 教师在本次固定的 12 条电商测试题上执行结果正确率为 50.00%，低于 LoRA 的 75.00%；这不表示 LoRA 的通用能力全面超过 API，而是说明 LoRA 更贴合当前数据库的字段、中文状态值和业务口径。两次 API 评估报告分别保存在 `outputs/evaluation_epoch2_api_run1.json` 和 `outputs/evaluation_epoch2_api_run2.json`。

## 一键运行

在项目根目录执行：

```powershell
python -m pip install -r requirements.txt
python app.py --self-test
python run_agent.py
python run_finetuning.py
```

`run_agent.py` 顶部的 `QUESTION` 有内容时执行单个问题；设为空字符串时进入连续提问模式。

## 复现步骤

### 1. 安装依赖

Python 3.10 或更高版本即可。使用 IDE 当前选择的项目解释器：

```powershell
python -m pip install -r requirements.txt
```

API 模式主要使用 `PyMySQL` 和 `truststore`。本地模式还需要 `torch`、`transformers` 和 `peft`。

### 2. 准备 Demo 数据

如果已经存在 `ecommerce_text_to_sql` 数据库，跳过本步骤。否则进入配套 Text-to-SQL 项目并初始化教学库：

```powershell
python init_mysql.py
```

初始化脚本会重建四张教学表，不要对包含重要数据的数据库运行。

### 3. 准备 Real 数据

本项目没有 Real 数据 profile，也不连接真实业务数据库。若要迁移到其他数据库，需要重新编写 `knowledge.py` 的表结构、外键和指标口径，并使用只读数据库账号。

### 4. 生成训练集和独立评测集

先用人工种子完成无 API 冒烟验证：

```powershell
python scripts/generate_distillation_data.py --seed-only
python scripts/prepare_evaluation_data.py
python scripts/train_student.py --check-data
```

要调用 API 教师生成多样化问法，并让 API 裁判自动审核：

```powershell
python scripts/generate_distillation_data.py --variants 4 --judge-min-confidence 0.95
```

每个种子只调用一次教师和一次批量裁判。裁判检查日期、数字阈值、排序方向、订单状态、Top-N、聚合口径和业务对象；只有 `equivalent=true` 且置信度达到阈值的改写自动进入训练集。裁判缺少判决、格式错误或请求失败时，对应改写直接拒绝。

裁判 API 配置留空时复用教师 API。规模化使用时推荐单独配置：

```python
JUDGE_API_BASE = "https://your-judge-provider.example/v1"
JUDGE_API_KEY = "your-judge-api-key"
JUDGE_MODEL = "your-judge-model"
JUDGE_MIN_CONFIDENCE = 0.95
```

### 5. 启动 Agent

IDE 一键运行：

```powershell
python run_agent.py
```

命令行单题运行：

```powershell
python app.py --question "统计各商品分类的销售额并按销售额降序排列"
```

连续提问：

```powershell
python app.py
```

### 6. 运行知识蒸馏实验

推荐在 `run_finetuning.py` 顶部设置 `ACTION` 后从 IDE 运行。也可以使用命令行：

```powershell
python scripts/train_student.py --model-path path/to/local-model --epochs 1 --output-dir outputs/student_lora
python scripts/evaluate_finetuning.py --model-path path/to/local-model --adapter-path outputs/student_lora
```

需要把 API 教师加入能力上限对比时，在评估命令末尾加 `--include-api`。严格判断微调是否有效，只比较报告中的“本地基础模型”和“LoRA 学生模型”。

使用 API 教师时，IDE 中依次选择 `generate`、`train`、`evaluate`，不再需要 `apply_reviews`。也可以选择 `all` 自动连续执行，但分步运行更方便观察裁判通过率和定位错误。训练脚本不会覆盖非空的适配器目录；重复实验需要填写新的 `ADAPTER_OUTPUT`。

## 大模型 Agent

模型只负责生成 SQL 计划和解释已执行结果。知识检索、SQL 安全校验、数据库连接、错误重试和输出格式都由本项目控制。

### 推荐方式

| 方案 | 推荐度 | 适用场景 | 说明 |
| --- | --- | --- | --- |
| 云端 API | 推荐 | Agent 演示、追求生成质量和启动速度 | 本机不加载模型；会发送问题、业务知识和查询结果，并产生调用费用。 |
| 本地 Qwen2.5-1.5B-Instruct | 推荐用于学习 | 离线流程、本地模型接口、CPU 推理 | 已完成最小生成验证；复杂 SQL 和结果解释弱于较强 API。 |
| 本地 Qwen + LoRA | 推荐用于微调实验 | 比较微调前后执行正确率 | 适配器必须与基础模型和提示模板匹配，不能只看输出是否更简洁。 |
| API 教师 + API 裁判 + 本地 LoRA 学生 | 当前主线 | 合成数据、自动质量过滤、黑盒知识蒸馏 | 推荐教师与裁判使用不同模型，并保留独立测试集。 |

### 云端 API

推荐直接修改根目录 `run_agent.py` 顶部配置区：

```python
LLM_MODE = "api"
LLM_API_BASE = "https://your-api-provider.example/v1"
LLM_API_KEY = "your-api-key"
LLM_MODEL = "your-model-name"
```

`LLM_API_BASE` 可以填写 API 根地址，也可以填写完整的 `/chat/completions` 地址。真实 Key 只保存在本机，不要提交到仓库、截图或聊天记录。

### 本地 Qwen

将模式切换为 `local`，并填写本地模型目录：

```python
LLM_MODE = "local"
LOCAL_MODEL_PATH = "path/to/Qwen2.5-1.5B-Instruct"
LOCAL_ADAPTER_PATH = ""
LOCAL_THREADS = "8"
LOCAL_MAX_NEW_TOKENS = "256"
```

`LOCAL_ADAPTER_PATH` 留空时使用基础模型；填写兼容的 LoRA 目录后使用微调模型。本地模型只在第一次调用时加载，API 模式不会导入模型权重。

### 合成数据与知识蒸馏

API 在微调项目中的价值不只是线上推理。较强 API 在本项目中充当教师模型，为人工标准问题生成多种等价问法；另一个 API 模型可充当裁判，批量判断语义一致性。标准 SQL 始终来自人工种子，避免教师自由编造字段和关联。本地 Qwen 是学生模型，通过 LoRA 学习经过筛选的数据。

蒸馏数据至少经过五道检查：JSON 格式、只读安全、MySQL 可执行、问题去重、API 裁判确认改写与标准问题语义一致。未经检查的大批 API 输出只是噪声扩增，不是高质量知识蒸馏。

`JUDGE_API_BASE`、`JUDGE_API_KEY`、`JUDGE_MODEL` 必须全部填写或全部留空；部分填写会直接报错，不会把教师密钥发送到裁判地址。

微调效果应按以下三组报告：

| 对照组 | 用途 | 是否用于严格判断微调效果 |
| --- | --- | --- |
| 本地基础模型 | 微调前基线 | 是 |
| 本地基础模型 + LoRA | 微调后学生模型 | 是 |
| API 教师模型 | 能力上限参考、数据生成和兜底 | 否，不是同一基础模型 |

只有“本地基础模型”和“同一基础模型加 LoRA”的差异能严格归因于微调。API 教师用于观察学生与强模型之间还有多大差距。

### 确认实际调用后端

查看 `run_agent.py` 的 `LLM_MODE`：

- `api`：调用 `LLM_API_BASE` 和 `LLM_MODEL` 指定的云端服务。
- `local` 且 `LOCAL_ADAPTER_PATH` 为空：使用本地基础模型。
- `local` 且填写 `LOCAL_ADAPTER_PATH`：使用本地基础模型和 LoRA。

本地模式启动时会显示权重加载进度；API 模式不会加载本地权重。终端随后输出检索到的知识、执行 SQL、查询表格、重试状态和分析结论。

## IDE 运行

1. 用 IDE 打开项目根目录。
2. 选择已经安装 `requirements.txt` 依赖的 Python 解释器。
3. 打开 `run_agent.py`，设置 `LLM_MODE` 和对应模型参数。
4. 修改 `QUESTION`，直接运行 `run_agent.py`。

不要把本机解释器、模型绝对路径或真实 API Key 写入共享运行配置。`run_agent.py` 是本机入口并已被 `.gitignore` 忽略；可分发模板为 `run_agent.example.py`。

## 项目结构

```text
ecommerce_data_agent/
├── run_agent.py             # 本机 IDE 一键入口，不提交真实配置
├── run_agent.example.py     # 可分发启动配置模板
├── run_finetuning.py        # 本机 IDE 一键微调入口，不提交真实配置
├── run_finetuning.example.py # 可分发微调入口模板
├── app.py                   # 命令行入口、连续提问和自检
├── agent.py                 # SQL 规划、工具调用、一次修复和结果解释
├── knowledge.py             # 表结构和指标口径的轻量检索
├── llm_client.py            # OpenAI-compatible API 与本地模型客户端
├── database.py              # SQL 安全检查、MySQL 执行和格式化输出
├── config.py                # `.env` 与环境变量配置
├── requirements.txt         # API 和本地模型依赖
├── scripts/
│   ├── distillation_data.py          # 人工种子、独立测试题和 JSONL 工具
│   ├── generate_distillation_data.py # API 改写、批量裁判、去重和执行过滤
│   ├── prepare_evaluation_data.py    # 生成人工独立测试集
│   ├── train_student.py              # CPU LoRA 学生模型训练
│   └── evaluate_finetuning.py        # 基础/LoRA/API 三方执行评估
├── data/
│   ├── distillation/         # 候选数据和已验证训练集
│   └── evaluation/           # 独立人工测试集
├── outputs/                  # LoRA 适配器和评估报告
├── docs/
│   └── 设计说明.md           # 中文架构说明
├── task_plan.md             # 项目实施计划
├── findings.md              # 项目发现记录
├── progress.md              # 验证与修改记录
└── README.md
```

## 输出文件

当前 Agent 默认把知识来源、SQL、查询结果和分析结论打印到终端，不生成持久化报告。业务数据保存在 MySQL 的四张教学表中。

蒸馏链路使用以下仓库相对路径：

```text
data/distillation/candidates.jsonl       # API 教师模型原始候选
data/distillation/verified_train.jsonl   # 去重且标准 SQL 执行校验后的训练集
data/evaluation/test.jsonl               # 与训练集隔离的测试题
outputs/student_lora*/                    # 不同实验的本地学生模型 LoRA 适配器
outputs/student_lora*/training_summary.json # 训练样本、轮数、更新次数和损失摘要
outputs/evaluation_epoch1.json            # epoch1 本地模型评测报告
outputs/evaluation_epoch2.json            # epoch2 本地模型评测报告
outputs/evaluation_epoch3.json            # epoch3 本地模型评测报告
outputs/evaluation_epoch2_api_run*.json   # epoch2 的重复 API 三方评测报告
```

`candidates.jsonl` 保存人工种子、API 改写、裁判判决和拒绝原因；`verified_train.jsonl` 只保存人工种子与裁判高置信通过的改写；`test.jsonl` 包含 12 条独立人工测试题。本次实验已经生成多组 LoRA 适配器、训练摘要和评估报告；重新实验时应为 `ADAPTER_OUTPUT` 和 `EVALUATION_OUTPUT` 指定新的名称，避免覆盖历史结果。

## 测试

```powershell
python app.py --self-test
python scripts/generate_distillation_data.py --seed-only
python scripts/prepare_evaluation_data.py
python scripts/train_student.py --check-data
python -m compileall .
```

当前自检覆盖知识检索、只读 SQL 规范化、危险 SQL 拒绝、重复 JSON 提取、SQL 多行排版、训练数据结构和标准 SQL 执行。本次完整训练和推理评估已经由用户运行完成，README 直接采用 `outputs/evaluation_*.json` 和各适配器训练摘要中的结果，没有重复执行耗时任务。

## 局限

- 业务知识只有 4 条关键词规则，不是向量数据库；换数据库后必须同步更新表结构和指标口径。
- 字符串级 SQL 校验不是完整 SQL 解析器，也不能替代只读账号、权限隔离、超时和审计。
- 1.5B 本地模型适合 CPU 学习和流程验证，复杂 SQL、JSON 稳定性和结果解释可能弱于较强 API。
- API 会接收问题、检索上下文和查询结果，存在费用、网络、隐私和服务商可用性约束。
- API 裁判仍可能误判，尤其在教师与裁判使用同一模型时；规模化使用推荐独立裁判模型、较高阈值和独立测试集。
- 当前评估集只有 12 条题，epoch2 的 75.00% 执行结果正确率只能说明本次小规模实验有提升，不能代表模型在其他数据库和复杂问题上的泛化能力。
- 三次实验引用了相同的数据文件路径，测试集内容一致；训练文件曾在不同时间点更新，训练摘要显示实际样本快照为 54、71、72 条，因此当前结果不能严格证明训练轮数与准确率之间的因果关系。
- 项目用于学习和算法实习展示，不应直接连接生产数据库。

## English Summary

Ecommerce-Data-Agent is a CPU-oriented Chinese Text-to-SQL fine-tuning and black-box distillation project for a fixed MySQL teaching database. A strong API teacher paraphrases human-authored questions while an API judge filters rewrites by semantic equivalence and confidence; verified SQL remains fixed. A local Qwen student is trained with PEFT LoRA and compared against the same base model on a separate human test set. Across the completed experiments, the best observed execution-result accuracy was 75.00% for the epoch2 adapter, compared with 33.33% for the base model and 50.00% for the API reference on the same 12-sample test set.

## 参考资料

- [Qwen2.5](https://huggingface.co/Qwen)
- [Transformers](https://huggingface.co/docs/transformers/)
- [PEFT LoRA](https://huggingface.co/docs/peft/)
- [PyMySQL](https://pymysql.readthedocs.io/)
- [MySQL](https://dev.mysql.com/doc/)
