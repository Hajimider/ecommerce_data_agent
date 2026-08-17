# 电商数据分析 Agent 与 Text-to-SQL 微调系统

## 一、引言

### 1、项目背景介绍

在电商数据分析场景中，业务人员通常使用自然语言提出问题，例如“统计各商品分类的销售额”或“查询库存少于 30 件的商品”。传统方式需要数据人员理解表结构、编写 SQL、执行查询并整理结果，沟通和分析成本较高。

本项目围绕中文 Text-to-SQL 任务，构建了“公开与领域数据准备、Qwen LoRA SFT 微调、独立执行评测、单个 Text-to-SQL Agent 落地”的完整链路。模型负责生成 SQL 和解释结果，Python 程序负责知识检索、安全校验、MySQL 查询、错误修复以及 Plotly 图表生成。

项目以本地 Qwen2.5-1.5B-Instruct 的 PEFT LoRA 微调为主，Agent 是微调模型的应用层。API 教师、API 裁判和 API 对照评估均为可选增强，没有 API 时仍可使用公开数据和人工领域数据完成训练、评估与本地推理。

### 2、目标与意义

本项目希望用一套可复现的小规模实验说明：如何让本地小模型学习数据库结构、中文业务状态值和电商指标口径，并通过真实 SQL 执行结果判断微调是否有效。

项目主要具有以下价值：

- **完成微调全流程**：覆盖数据构造、聊天模板、LoRA SFT、适配器保存和多轮实验对比。

- **使用执行结果评估**：不仅比较生成文本，还将 SQL 放入真实数据库执行，判断结果是否正确。

- **引入公开数据验证**：接入 CSpider 中文 Text-to-SQL 数据，补充自建电商数据以外的跨数据库样本。

- **提供应用落地层**：将微调模型接入单个 Agent，完成知识检索、SQL 生成、执行、修复和结果解释。

- **支持本地与 API 切换**：本地模式用于验证 LoRA，API 模式用于可选的数据生成、自动审核和能力参考。

- **便于 Demo 展示**：提供 Streamlit 浏览器页面，并支持查询成功后自动生成 Plotly 图表。

### 3、主要功能

本项目当前支持以下功能：

- Qwen2.5-1.5B-Instruct 基础模型与 LoRA 学生模型对比。
- CSpider 公开子集与电商领域数据的合并训练。
- API 教师生成等价问法、API 裁判自动审核和高置信度过滤。
- MySQL 电商测试集与 CSpider SQLite dev 子集分开评估。
- 单条 `SELECT` 安全检查、危险 SQL 拦截和一次错误修复。
- API 模型与本地 Qwen/LoRA 模型切换。
- SQL 多行格式化、结果表格和中文分析结论输出。
- 根据查询结果自动选择柱状图、折线图、饼图、散点图、指标卡或数据表。
- Streamlit 页面直接展示在线查询、执行结果、自动图表和微调前后指标。

**核心实验结果**

| 模型 | 执行结果正确率 | SQL 可执行率 | Agent 首次成功率 |
| --- | ---: | ---: | ---: |
| 本地基础模型 | 33.33% | 91.67% | 83.33% |
| 最佳 LoRA 模型 | 75.00% | 91.67% | 91.67% |
| 变化 | +41.67 个百分点 | 0.00 个百分点 | +8.34 个百分点 |

以上结果来自固定的 12 条电商独立测试题。该规模适合教学验证，不代表模型在其他数据库上的通用水平。

**Agent 运行效果示意**

```text
用户问题：查询已完成订单中销量最高的 3 个商品

检索业务知识
  -> 生成 SELECT SQL
  -> 安全检查
  -> MySQL 执行
  -> 返回结果表格与中文结论
  -> 自动生成并打开 Plotly 图表
```

## 二、技术实现

### 1、环境依赖

#### 1.1 技术资源要求

- **Python**：3.10 或更高版本。

- **数据库**：MySQL 8.x，用于电商领域训练数据校验、Agent 查询和领域评测。

- **本地模型**：Qwen2.5-1.5B-Instruct；Agent 演示和小规模训练可以在 CPU 环境运行，但训练耗时取决于处理器和内存。

- **公开评测数据库**：SQLite，由 Python 标准库调用，用于 CSpider 固定 dev 子集评测。

- **操作系统**：Windows、macOS 或 Linux，命令示例统一使用通用 `python`。

#### 1.2 项目设置

**安装项目依赖**

```shell
cd ecommerce_data_agent
python -m pip install -r requirements.txt
```

**准备本地配置**

复制 `.env.example` 为 `.env`，填写实际需要的配置。真实密码和 API Key 只保存在本机，不要提交到 GitHub。

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=ecommerce_text_to_sql

LLM_MODE=local
LOCAL_MODEL_PATH=path/to/local-model
LOCAL_ADAPTER_PATH=path/to/lora-adapter
```

API 模式可以填写兼容 OpenAI Chat Completions 格式的服务：

```dotenv
LLM_MODE=api
LLM_API_BASE=https://your-provider.example/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
```

#### 1.3 项目运行

**运行基础自检**

```shell
python app.py --self-test
python visualization.py --self-test
```

**启动 Text-to-SQL Agent**

```shell
python run_agent.py
```

**启动浏览器 Demo**

```shell
python run_demo.py
```

也可以使用通用 Streamlit 命令启动：

```shell
python -m streamlit run streamlit_app.py
```

**一键对比基础模型与 LoRA**

```shell
python run_compare.py
```

**启动微调流程入口**

```shell
python run_finetuning.py
```

**生成固定业务看板**

```shell
python run_visualization.py
```

### 2、开发流程简述

#### 2.1 当前项目版本及未来规划

- **当前版本**：最新版实验与 Agent 可视化版本。

  - **已完成内容**
    - [√] CSpider 公开数据转换、固定抽样和训练快照生成。
    - [√] 电商领域人工标准数据与独立测试集。
    - [√] API 合成问法、批量裁判、SQL 执行过滤和去重。
    - [√] Qwen2.5-1.5B-Instruct PEFT LoRA SFT 训练。
    - [√] Base、LoRA 与可选 API 教师的 MySQL 执行评测。
    - [√] CSpider Base/LoRA SQLite 轻量执行评测。
    - [√] 单个 Text-to-SQL Agent 与本地/API 双后端。
    - [√] 查询结果自动选择 Plotly 图表并打开本地 HTML。
    - [√] 金额指标卡中文标题、货币符号和两位小数格式。
    - [√] Streamlit 在线查询与微调效果对比 Demo。

- **后续可扩展方向**

  - [ ] 使用更大且固定的数据快照完成严格单变量训练实验。
  - [ ] 引入 SQL AST 解析器，替代部分字符串级安全检查。
  - [ ] 增加数据库只读账号、查询超时和审计日志。
  - [ ] 扩大独立测试集，增加复杂连接、子查询和窗口函数任务。

#### 2.2 核心 Idea

项目核心不是让模型直接控制数据库，而是让模型只完成受约束的 SQL 规划和结果解释，其余步骤由确定性 Python 代码完成。微调前后的模型使用相同提示模板、相同测试集和相同数据库，通过执行结果正确率判断 LoRA 是否有效。

整体流程如下：

```text
CSpider 公开数据 + 电商领域数据
  -> 固定训练快照
  -> Qwen LoRA SFT
  -> CSpider SQLite / 电商 MySQL 分开评测
  -> 单个 Text-to-SQL Agent
  -> SQL 执行结果、中文结论和 Plotly 图表
```

#### 2.3 使用的技术栈

本项目使用 Python 构建，核心技术包括 PyTorch、Transformers、PEFT LoRA、Qwen2.5、MySQL、SQLite、OpenAI-compatible API、JSONL 和 Plotly。

项目从底向上分为五层：

① **数据层**：保存 CSpider 固定子集、电商领域训练集、独立测试集和 API 合成候选数据。

② **模型层**：使用 Transformers 加载 Qwen 基础模型，通过 PEFT LoRA 完成 SFT，并支持挂载适配器推理。

③ **评测层**：分别在 MySQL 和 SQLite 中执行预测 SQL，统计 JSON/SQL 提取率、SQL 可执行率和执行结果正确率。

④ **Agent 层**：检索表结构和指标口径，调用模型生成 SQL，执行安全检查，并在失败时修复一次。

⑤ **展示层**：终端显示知识来源、SQL、结果表格和结论，Plotly 自动生成交互式 HTML 图表。

## 三、应用详解

### 1、核心架构

本项目是一个以微调为主、Agent 为落地层的中文 Text-to-SQL 系统。Agent 没有拆分为 Planner、SQL、Review 等多个角色，避免与其他多 Agent 项目重复，也减少不必要的模型调用。

完整 Agent 数据流如下：

1. 用户输入中文电商分析问题。
2. 根据问题关键词检索表结构、外键关系和业务指标口径。
3. API 或本地 Qwen 返回 `{"sql":"SELECT ...;"}`。
4. 程序拒绝非 `SELECT`、危险关键字、注释和多条语句。
5. MySQL 执行 SQL，最多返回 100 行结果。
6. 首次规划或执行失败时，将错误信息交给模型修复一次。
7. 模型读取已执行结果并生成简洁中文结论。
8. Python 根据结果字段自动选择 Plotly 图表并打开 HTML。

项目明确限定为教学数据库，不应直接连接生产数据库或处理真实敏感数据。

### 2、数据准备与微调

#### 2.1 数据集构建

项目采用“CSpider 公开数据 + 电商领域数据”的双数据集设计，两类数据使用不同数据库引擎评测，指标不混算。

| 数据集 | 用途 | 当前实验规模 | 评测方式 |
| --- | --- | ---: | --- |
| CSpider | 学习中文跨数据库 SQL 结构并测试公开泛化 | train 200 条、dev 50 条 | SQLite 轻量执行对比 |
| 电商领域训练集 | 学习 MySQL 方言、表关系和中文业务状态 | 当前文件 72 条 | 只用于训练，不直接充当测试集 |
| 电商独立测试集 | 检查领域 Text-to-SQL 效果 | 12 条 | MySQL 执行结果对比 |

CSpider 通过固定随机种子抽样，生成的训练摘要记录数据来源数量和 SHA-256。当前固定合并训练快照共 272 条，其中包括 200 条公开训练样本和 72 条电商领域样本。

CSpider 的部分数据库 Schema 较长。训练编码器超过 `MAX_LENGTH` 时会裁剪提示词中间的 Schema，同时保留系统规则、用户问题和完整标准 SQL；当前 272 条训练快照中有 19 条触发该处理。

#### 2.2 合成数据与自动审核

电商领域数据首先由人工编写标准问题和 SQL。可选 API 教师只负责生成语义等价问法，标准 SQL 继续沿用人工标签，避免教师自由编造字段。

合成候选依次经过以下检查：

1. JSON 格式检查。
2. 单条 `SELECT` 安全检查。
3. MySQL 可执行验证。
4. 问题去重。
5. API 裁判检查日期、阈值、排序、状态、Top-N、聚合口径和业务对象。
6. 仅保留 `equivalent=true` 且置信度达到阈值的样本。

本次已记录实验中，API 教师共生成并审核 63 条候选，最终保留 54 条高置信训练样本。API 失败、格式异常或裁判缺少判决时，候选直接拒绝。

#### 2.3 Qwen LoRA SFT

训练脚本使用 Qwen 聊天模板，将表结构、业务知识和用户问题组织为输入，assistant 输出统一为 JSON SQL。训练时只对 assistant 答案计算损失，不让模型学习 system 和 user 提示文本。

LoRA 只训练少量低秩参数，不修改完整基础模型权重。不同实验将适配器保存到独立目录，便于比较不同轮数并保留基础模型基线。

推荐通过 `run_finetuning.py` 顶部配置执行：

```python
ACTION = "train"                 # generate、prepare_public、train、evaluate、evaluate_public 或 all
EPOCHS = 2
ADAPTER_OUTPUT = "outputs/student_lora_epoch2"
EVALUATION_OUTPUT = "outputs/evaluation_epoch2.json"
```

`apply_reviews` 仅用于可选人工覆盖，不属于默认自动流程。

公开数据实验可以依次运行：

```text
prepare_public -> train -> evaluate -> evaluate_public
```

不建议在 Demo 现场重新训练。展示时直接使用已有适配器和评估报告即可。

### 3、模型评估

#### 3.1 电商 MySQL 独立测试

电商评估使用 12 条未参与训练的测试题，对比同一本地基础模型与加载 LoRA 后的学生模型。已有三次完整实验结果如下：

| 评估报告 | 训练样本数 | LoRA 轮数 | 执行结果正确率 | SQL 可执行率 | Agent 首次成功率 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `evaluation_epoch1.json` | 54 | 1 | 58.33% | 91.67% | 75.00% |
| `evaluation_epoch2.json` | 71 | 2 | 75.00% | 91.67% | 91.67% |
| `evaluation_epoch3.json` | 72 | 3 | 66.67% | 83.33% | 83.33% |

三份报告中的本地基础模型基线一致：执行结果正确率 33.33%、SQL 可执行率 91.67%、Agent 首次成功率 83.33%。当前最佳 LoRA 实验为 epoch2，执行结果正确率达到 75.00%，较基础模型提升 41.67 个百分点。

三次实验使用相同文件路径和同一测试集，但训练文件曾在不同时间重新生成，实际训练样本快照分别为 54、71、72 条。因此这些结果可以比较三次完整实验，不能将差异严格归因于训练轮数。严格单变量实验应先固定训练快照，再分别训练不同 epoch。

#### 3.2 API 教师对照

epoch2 的 API 教师对照评估连续运行两次，结果一致：

| 指标 | 本地基础模型 | LoRA 学生模型 | API 教师模型 |
| --- | ---: | ---: | ---: |
| JSON/SQL 提取率 | 100.00% | 100.00% | 100.00% |
| SQL 可执行率 | 91.67% | 91.67% | 100.00% |
| 执行结果正确率 | 33.33% | 75.00% | 50.00% |
| Agent 首次成功率 | 83.33% | 91.67% | 100.00% |
| Agent 重试率 | 16.67% | 8.33% | 0.00% |

API 教师不是同一基础模型，不能用于严格判断 LoRA 的提升。它只用于生成数据、自动审核和提供能力参考。API 在当前 12 条电商题上低于 LoRA，说明本地学生更贴合当前数据库口径，不代表学生模型的通用能力超过云端模型。

#### 3.3 CSpider 公开子集评估

使用 200 条 CSpider 训练子集和 72 条电商领域样本训练 epoch2 适配器，并在固定抽取的 50 条 CSpider dev 上评估：

| 指标 | 本地基础模型 | LoRA 学生模型 | 变化 |
| --- | ---: | ---: | ---: |
| JSON/SQL 提取率 | 100.00% | 100.00% | 0.00 个百分点 |
| SQL 可执行率 | 72.00% | 66.00% | -6.00 个百分点 |
| 轻量执行结果正确率 | 46.00% | 48.00% | +2.00 个百分点 |
| 平均每题耗时 | 19.44 秒 | 13.71 秒 | -5.73 秒 |

该结果说明小规模混合训练只带来了有限的公开集正确率提升，同时 SQL 可执行率下降，不能宣称泛化能力显著提高。典型错误仍包括字段幻觉、关联遗漏、聚合条件错误和 SQLite/MySQL 函数混用。

#### 3.4 典型错误分析

| 模型 | 典型错误 | 影响 |
| --- | --- | --- |
| 基础模型 | 将中文状态“退款中”“已完成”生成成 `refunded`、`completed` | SQL 可以执行但返回错误结果 |
| 基础模型 | 将销量 `SUM(quantity)` 错写为明细行数 `COUNT(item_id)` | 聚合口径错误 |
| 基础模型 | 将分组聚合条件写成普通 `WHERE` | 无法正确筛选累计金额 |
| LoRA 模型 | 复杂关联时偶尔引用不存在的表别名 | SQL 执行失败 |
| LoRA 模型 | 将库存金额误解为历史销售额 | 业务指标口径混淆 |

错误分析来自现有 `evaluation_epoch*.json` 报告，不额外编造测试结果。LoRA 明显改善了中文状态、表关系和常见聚合，但复杂聚合与业务口径仍是主要优化方向。

### 4、单个 Text-to-SQL Agent

#### 4.1 业务知识检索

`knowledge.py` 保存四类电商业务知识：数据库结构与关联、销售额与销量口径、订单与用户分析口径、库存与商品分析口径。

程序按照问题中的“销售额”“订单”“城市”“库存”等词项计算命中分数，最多选择 3 条知识。没有关键词命中时返回基础表结构。该方式适合固定教学库，不是向量数据库，也不构成完整 RAG 系统。

订单状态必须使用数据库中的中文原值：`已完成`、`待付款`、`退款中`、`已取消`。Agent 会拒绝模型生成的 `completed` 等错误值并尝试修复，避免聚合查询静默返回 `NULL`。

#### 4.2 SQL 生成与安全检查

模型只允许返回一个 JSON 对象：

```json
{"sql":"SELECT product_name, stock FROM products WHERE stock < 30 ORDER BY stock ASC;"}
```

执行前会完成以下检查：

- 必须以 `SELECT` 开头。
- 拒绝 `INSERT`、`UPDATE`、`DELETE`、`DROP`、`ALTER` 等危险关键字。
- 拒绝 SQL 注释和多条语句。
- 每次最多读取 100 行。
- 第一次规划或执行失败时携带错误信息修复一次，第二次失败后停止。

字符串级检查只是教学防线，不能替代数据库只读账号、最小权限、查询超时和审计。

#### 4.3 本地模型与 API 切换

`run_agent.py` 顶部集中配置模型后端：

```python
LLM_MODE = "local"              # local 或 api
LOCAL_MODEL_PATH = "path/to/local-model"
LOCAL_ADAPTER_PATH = "path/to/lora-adapter"
```

- `local` 且适配器路径为空：使用本地基础模型。
- `local` 且填写适配器路径：使用本地基础模型和 LoRA。
- `api`：调用配置的 OpenAI-compatible API，不加载本地权重。

只有“本地基础模型”和“同一基础模型 + LoRA”的差异能严格归因于微调。

#### 4.4 查询结果与自动可视化

Agent 会在终端依次输出检索到的知识、格式化 SQL、查询结果、重试状态和中文结论。查询成功后，Python 根据结果结构自动选图，大模型不生成绘图代码。

| 结果结构 | 自动图表 |
| --- | --- |
| 单行单个数值 | 指标卡 |
| 时间字段 + 数值字段 | 折线图 |
| 状态/类型 + 数值，类别较少 | 饼图 |
| 分类字段 + 数值字段 | 柱状图 |
| 两个数值字段 | 散点图 |
| 其他结构 | 数据表 |

金额指标卡会显示中文标题、人民币符号、千分位和两位小数。空结果或全 `NULL` 结果不会生成误导图表，而是提示检查 SQL 筛选条件。

### 5、Demo 展示

#### 5.1 浏览器 Demo

直接运行 `run_demo.py`，浏览器会打开 Streamlit 页面：

```shell
python run_demo.py
```

页面包含两个视图：

- **在线查询**：选择 LoRA、本地基础模型或 API 模型，输入自然语言问题后展示格式化 SQL、MySQL 查询结果、中文结论、业务知识来源和自动图表。
- **微调对比**：直接读取已有评估报告，展示基础模型与 LoRA 的执行结果正确率、SQL 可执行率、Agent 首次成功率和单题 SQL 对比，无需现场重新训练。

本地模型和 LoRA 路径、API 配置以及 MySQL 连接信息统一从 `.env` 读取。页面同一时间只缓存一个模型后端，切换模型时不会主动让基础模型与 LoRA 同时常驻内存。

#### 5.2 微调前后对比 Demo

`run_compare.py` 从现有独立测试集中选择一道题，依次运行基础模型和 LoRA。程序会展示标准 SQL、标准执行结果、两种模型的预测 SQL、执行结果、正确性和耗时。

```python
MODEL_PATH = ""  # 留空时读取 .env
ADAPTER_PATH = "outputs/student_lora_epoch2"
TEST_CASE_ID = "test_completed_month_count"
```

运行：

```shell
python run_compare.py
```

基础模型执行完成并释放内存后才会加载 LoRA，不会让两个 1.5B 模型同时驻留内存。该入口只测试一题，适合现场展示，不替代完整评估报告。

**本次实际运行示例**

问题：`按月份统计已完成订单数`

| 对比项 | 本地基础模型 | LoRA 微调模型 |
| --- | --- | --- |
| SQL 可执行 | 是 | 是 |
| 执行结果正确 | 是 | 是 |
| SQL 完整性 | 缺少显式 `ORDER BY`，字段别名不同 | 与标准 SQL 一致 |
| 本次运行耗时 | 117.33 秒 | 24.86 秒 |

基础模型 SQL：

```sql
SELECT
    DATE_FORMAT(order_date, '%Y-%m') AS month,
    COUNT(*) AS complete_orders
FROM orders
WHERE status = '已完成'
GROUP BY month;
```

LoRA 微调模型 SQL：

```sql
SELECT
    DATE_FORMAT(order_date, '%Y-%m') AS order_month,
    COUNT(*) AS order_count
FROM orders
WHERE status = '已完成'
GROUP BY order_month
ORDER BY order_month;
```

两种模型均得到 `2025-01` 至 `2025-05` 的正确订单数 `2、1、2、1、2`。LoRA 输出的字段别名、排序和 SQL 结构更贴近标准答案；耗时包含模型加载、系统缓存和 CPU 状态，只作为单次运行记录，不作为推理性能结论。

#### 5.3 Agent 查询 Demo

修改 `run_agent.py` 中的测试问题，然后直接运行：

```python
TEST_QUESTIONS = [
    "统计各商品分类的销售额并按销售额降序排列",
    "按城市统计已完成订单的销售额",
    "按月份统计全部订单金额",
    "统计每种订单状态的订单数量",
    "查询已完成订单中销量最高的 3 个商品",
    "查询库存少于 30 件的商品，按库存升序排列",
    "统计每位用户的订单总金额，按总金额降序排列",
    "计算已完成订单的平均金额",
]

QUESTION = TEST_QUESTIONS[0]
AUTO_CHART = True
OPEN_CHART = True
```

运行：

```shell
python run_agent.py
```

设置 `QUESTION = ""` 后进入连续提问模式。每次成功查询都会在 `outputs/charts/queries/` 生成独立 HTML，并按配置自动打开。

#### 5.4 固定业务看板 Demo

运行：

```shell
python run_visualization.py
```

程序将 5 个固定业务指标合并到 `outputs/charts/dashboard.html`，包括分类销售额、城市销售额、订单状态、库存价值和月度销售趋势。

#### 5.5 微调效果 Demo

现场展示不需要重新训练模型。推荐直接打开以下报告，对比基础模型与 LoRA：

```text
outputs/evaluation_epoch1.json
outputs/evaluation_epoch2.json
outputs/evaluation_epoch3.json
outputs/evaluation_cspider_epoch2.json
```

演示时重点说明：电商独立测试中最佳 LoRA 执行结果正确率为 75.00%，基础模型为 33.33%；CSpider 固定子集仅提升 2 个百分点且可执行率下降，项目对不同数据域分别报告结果，没有合并或夸大指标。

### 6、项目结构

```text
ecommerce_data_agent/
├── run_demo.py              # IDE 一键启动 Streamlit Demo
├── streamlit_app.py         # 在线查询与微调对比页面
├── run_agent.py             # IDE 一键 Agent 入口
├── run_compare.py           # IDE 一键 Base/LoRA 单题对比入口
├── run_finetuning.py        # IDE 一键数据、训练和评估入口
├── run_visualization.py     # IDE 一键生成 Plotly 看板
├── app.py                   # 命令行、连续提问、自动图表和自检
├── agent.py                 # SQL 规划、业务校验、执行重试和结果解释
├── database.py              # SQL 安全检查、MySQL 执行和格式化
├── knowledge.py             # 表结构和指标口径的轻量检索
├── llm_client.py            # OpenAI-compatible API 与本地模型客户端
├── visualization.py         # 固定看板和单次查询图表
├── config.py                # `.env` 与环境变量配置
├── requirements.txt
├── scripts/
│   ├── distillation_data.py
│   ├── generate_distillation_data.py
│   ├── prepare_evaluation_data.py
│   ├── prepare_cspider.py
│   ├── train_student.py
│   ├── evaluate_finetuning.py
│   └── evaluate_cspider.py
├── data/
│   ├── distillation/        # 候选数据和已验证训练集
│   ├── public/cspider/      # CSpider 目录说明，原始数据不提交
│   ├── training/            # 固定合并训练快照
│   └── evaluation/          # 电商与 CSpider 独立测试集
├── outputs/                 # 评估报告；权重和图表由本机生成
├── docs/                    # 设计、使用说明和面试材料
└── README.md
```

### 7、测试

```shell
python app.py --self-test
python run_compare.py --self-test
python visualization.py --self-test
python -m streamlit run streamlit_app.py
python scripts/generate_distillation_data.py --seed-only
python scripts/prepare_evaluation_data.py
python scripts/train_student.py --check-data
python scripts/prepare_cspider.py --self-test
python scripts/evaluate_cspider.py --self-test
python -m compileall -q scripts app.py agent.py config.py database.py knowledge.py llm_client.py visualization.py run_agent.py run_compare.py run_demo.py run_finetuning.py run_visualization.py streamlit_app.py
```

当前自检覆盖知识检索、业务状态值、只读 SQL 规范化、危险操作拒绝、SQL 多行排版、训练数据结构、公开数据转换、自动选图和金额指标卡格式。

## 四、总结与展望

### 1、项目关键点总结

本项目完成了一个可运行、可评测、可展示的中文 Text-to-SQL 微调案例，关键点包括：

1. 使用 CSpider 公开数据和电商领域数据构建固定训练快照。
2. 使用 Qwen2.5-1.5B-Instruct 与 PEFT LoRA 完成 SFT 微调。
3. 使用独立数据库执行结果评估 Base 与 LoRA，而不是只观察训练损失。
4. 使用可选 API 教师扩充问法，并通过 API 裁判和 SQL 执行过滤数据。
5. 使用单个 Text-to-SQL Agent 完成模型能力落地，避免不必要的多 Agent 编排。
6. 使用 Streamlit 与 Plotly 展示查询、SQL、结果、图表和微调前后指标，形成可现场演示的完整分析链路。

### 2、项目局限

- 电商独立测试集只有 12 条，75.00% 只代表本次小规模实验。
- CSpider 默认使用固定子集和项目自建的轻量执行评测，不等同于官方全量榜单。
- 业务知识只有 4 条关键词规则，不是向量数据库，换库后必须更新 Schema 和指标口径。
- 1.5B 模型适合教学和 CPU 流程验证，复杂 SQL 能力仍有限。
- 字符串级 SQL 安全检查不能替代只读权限、查询超时、审计和隔离环境。
- API 会产生费用，并可能发送问题、上下文和查询结果，使用时需要考虑隐私。
- 现有不同 epoch 实验的训练样本快照不完全一致，不能严格证明 epoch 与准确率的因果关系。

### 3、未来发展方向

- 固定更大规模的训练快照，完成严格的 epoch、LoRA rank 和学习率对照实验。
- 增加复杂连接、子查询、窗口函数和多条件业务问题。
- 使用 SQL AST 完成更可靠的只读检查和表字段白名单验证。
- 增加只读数据库账号、查询超时、轨迹日志和可复现的错误分析报告。
- 将 Streamlit Demo 部署为可公开访问的临时演示地址，避免面试展示依赖本机环境。

## 五、参考资料与致谢

感谢以下开源模型、框架、数据集和工具为项目提供基础能力：

- [Qwen2.5](https://huggingface.co/Qwen)
- [Transformers](https://huggingface.co/docs/transformers/)
- [PEFT LoRA](https://huggingface.co/docs/peft/)
- [PyTorch](https://pytorch.org/)
- [MySQL](https://dev.mysql.com/doc/)
- [PyMySQL](https://pymysql.readthedocs.io/)
- [Plotly](https://plotly.com/python/)
- [Streamlit](https://streamlit.io/)
- [CSpider](https://github.com/taolusi/chisp)

本项目用于大模型微调、Text-to-SQL 和算法工程实践，不构成真实经营决策建议，也不应直接连接生产数据库。
