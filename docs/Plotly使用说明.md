# Plotly 交互式图表

## 数据来源

图表使用项目已有的 `ecommerce_text_to_sql` MySQL 教学数据库。Plotly 支持固定业务总览和单次 Agent 查询结果两种输出；LoRA 训练集与 CSpider SQLite 数据不作为电商图表数据源。

```text
MySQL 教学库
  -> 固定 SELECT 汇总 -> outputs/charts/dashboard.html
  -> Agent 动态查询 -> outputs/charts/queries/query_*.html
  -> Windows 文件关联自动打开本地 HTML
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
| `queries/query_*.html` | 每次电商 Agent 查询生成的独立图表 |

每次运行脚本都会重新查询 MySQL 并覆盖总览 HTML，适合数据更新后的快速刷新。统计值由 SQL 计算，模型只负责自然语言查询和解释，不直接生成数值。

## Agent 自动图表

打开 `run_agent.py`，保持以下配置：

```python
AUTO_CHART = True
OPEN_CHART = True
CHART_OUTPUT_DIR = "outputs/charts/queries"
```

运行后，Agent 会先完成 SQL 生成、MySQL 查询和中文结论，再根据结果自动选择图表并打开 HTML。连续提问模式下每个问题生成一个带时间戳的新文件，不覆盖之前的图表。

| 查询结果结构 | 自动图表 |
| --- | --- |
| 分类、城市、商品或用户 + 数值 | 柱状图 |
| 日期或月份 + 数值 | 折线图 |
| 状态或类型 + 数值，且类别不超过 8 个 | 饼图 |
| 两个数值字段 | 散点图 |
| 单行单指标 | 指标卡 |
| 空结果或不适合绘图 | 数据表 |

大模型不生成 Python 或 Plotly 代码，自动选图和 HTML 导出由固定程序完成。若只想查看终端结果，将 `AUTO_CHART` 设为 `False`；若只想生成文件而不自动打开，将 `OPEN_CHART` 设为 `False`。

## 测试问题

```text
统计各商品分类的销售额并按销售额降序排列
按城市统计已完成订单的销售额
按月份统计全部订单金额
统计每种订单状态的订单数量
查询已完成订单中销量最高的 3 个商品
查询库存少于 30 件的商品，按库存升序排列
统计每位用户的订单总金额，按总金额降序排列
计算已完成订单的平均金额
```

这些问题已经保存在 `run_agent.py` 的 `TEST_QUESTIONS` 中，可通过修改 `QUESTION = TEST_QUESTIONS[下标]` 逐个测试。

## 公开数据集扩展

CSpider 公开数据用于训练和 SQLite 泛化评测，不接入当前电商 Agent 自动图表。若未来为 CSpider 增加交互查询，需要根据 `db_id` 动态加载数据库和 Schema，并单独处理 SQLite 方言，不能复用电商指标口径。
