# CSpider 公开数据集接入设计

## 目标

在不改变现有电商 MySQL 领域实验的前提下，引入公开中文 Text-to-SQL 数据集 CSpider，补充跨数据库 SQL 结构学习和公开数据上的泛化评测。项目仍以 Qwen LoRA SFT、严格对照评测和错误分析为主，单个 Text-to-SQL Agent 仅作为落地演示。

## 方案

项目保留两条相互隔离的数据与评测链路：

```text
CSpider 公开训练子集 + 电商领域训练集
  -> 固定合并快照
  -> Qwen LoRA SFT
  -> CSpider dev 子集 SQLite 轻量执行评测
  -> 电商独立测试集 MySQL 执行评测
```

- CSpider 用于证明模型接触过公开、跨数据库、包含多种 SQL 结构的监督数据。
- 电商训练集用于学习当前业务表结构、中文状态值和指标口径。
- CSpider dev 与电商 12 条测试题分别报告，不合并成一个准确率。
- 公开评测采用固定随机种子抽样，并记录样本数量和数据快照，保证 Base 与 LoRA 使用完全相同的样本。

## 文件边界

- `scripts/prepare_cspider.py`：读取标准 Spider 格式的 `train.json`、`dev.json`、`tables.json` 和 SQLite 数据库，生成训练快照与公开评测集。
- `scripts/evaluate_cspider.py`：比较同一基础模型与 LoRA 在公开 dev 子集上的 JSON 提取率、SQL 可执行率和轻量执行结果正确率。
- `run_finetuning.py`：增加公开数据准备和公开评测操作，继续支持 IDE 顶部集中配置。

原始 CSpider 数据不提交 GitHub，只提交处理脚本、目录说明和小型统计清单。公开数据的许可证与使用条件以数据集原始发布页为准。

## 约束

- 默认只抽取适合本机 CPU 实验的小规模子集，不宣称完成 CSpider 官方全量榜单评测。
- 公开数据中的 SQLite SQL 不在 MySQL 中执行，两种方言分别评测。
- 现有 epoch1、epoch2、epoch3 指标属于旧的纯电商训练实验，接入公开数据后必须使用新适配器和新报告名，不能沿用旧指标。
- 不新增 RAG、多 Agent、LangChain 或云端推理依赖，避免与已有项目重叠。

## 验收

1. 在没有模型和 MySQL 的情况下，数据转换自检可运行。
2. 训练脚本能检查合并后的 JSONL，且允许不同数据库出现相同自然语言问题。
3. 公开评测报告明确标注为 CSpider dev 子集轻量执行评测。
4. README 不包含本机绝对路径、用户名、解释器路径或真实密钥。
