# CSpider 原始数据目录

本项目不重复分发 CSpider 原始数据。请遵守数据集原始许可证，从 CSpider 发布方或合法镜像获取标准 Spider 格式文件，并放置为：

```text
data/public/cspider/raw/
├── train.json               # 也兼容 train_spider.json
├── dev.json
├── tables.json
└── database/
    └── <db_id>/
        └── <db_id>.sqlite
```

随后在项目根目录运行：

```powershell
python scripts/prepare_cspider.py --public-train-samples 200 --public-dev-samples 50
```

脚本只读取原始数据，使用固定随机种子生成公开训练子集、公开 dev 子集以及与电商领域数据合并的训练快照。原始数据和生成的大型 JSONL 已被 `.gitignore` 排除。
