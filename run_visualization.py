"""IDE 一键生成 Plotly 交互式图表。"""

from visualization import export_charts


# 修改配置后直接运行本文件。
OUTPUT_DIR = "outputs/charts"
COMPLETED_STATUS = "已完成"
OPEN_BROWSER = True


def main():
    manifest = export_charts(output_dir=OUTPUT_DIR, completed_status=COMPLETED_STATUS, open_browser=OPEN_BROWSER)
    print(f"Plotly 图表已生成到：{OUTPUT_DIR}")
    print(f"已生成总览页面：{OUTPUT_DIR}/dashboard.html（包含 {len(manifest['charts'])} 个图表）。")


if __name__ == "__main__":
    main()
