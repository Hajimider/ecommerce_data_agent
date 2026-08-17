"""IDE 一键启动 Streamlit Demo。"""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PORT = 8501


if __name__ == "__main__":
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "streamlit_app.py"),
            "--server.port",
            str(PORT),
        ],
        cwd=ROOT,
        check=True,
    )
