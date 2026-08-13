# Plotly 交互式图表

## 数据来源

图表使用项目已有的 `ecommerce_text_to_sql` MySQL 教学数据库。Python 固定执行只读汇总 SQL，Plotly 负责生成交互式 HTML；LoRA 训练集不作为图表数据源。

```text
MySQL 教学库
  -> visualization.py 固定 SELECT 汇总
  -> outputs/charts/dashboard.html
  -> 浏览器打开一个包含全部图表的总览页面
```

## 使用方式

命令行自检：

```powershell
python visualization.py --self-test
```

IDE 一键生成：

```python
# run_visualization.py
OUTPUT_DIR = "outputs/charts"
COMPLETED_STATUS = "已完成"
OPEN_BROWSER = False
```

直接运行 `run_visualization.py` 后，打开 `outputs/charts/dashboard.html` 即可查看全部图表。

将 `run_visualization.py` 中的 `OPEN_BROWSER` 改为 `True`，脚本会直接打开本地总览页面；如果浏览器仍显示默认首页，可手动双击 `dashboard.html`，不影响图表生成。

也可以命令行生成并自动打开浏览器：

```powershell
python visualization.py --output-dir outputs/charts --open-browser
```

## 图表说明

| 文件 | 内容 |
| --- | --- |
| `dashboard.html` | 包含全部 5 个图表的交互式总览页面 |
| `index.json` | 图表文件、数据行数和字段清单 |

每次运行脚本都会重新查询 MySQL 并覆盖总览 HTML，适合数据更新后的快速刷新。统计值由 SQL 计算，模型只负责自然语言查询和解释，不直接生成数值。

## 与 Agent 的关系

当前图表使用固定业务查询，保证图表字段和口径稳定。它是单个 Text-to-SQL Agent 之外的结果展示组件，不参与模型训练，也不需要拆分成额外的可视化 Agent。

## 公开数据集扩展

接入 Olist 等公开数据时，应先将原始 CSV 清洗后导入独立数据库，再为图表查询编写对应 SQL。不要直接把外部字段混入当前教学库，以免影响既有微调训练和评估。
