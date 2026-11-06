"""兼容入口：实际服务器实现在项目根的 server.py（云端发布也用它）。

用法：python scripts/serve.py 8000   或   python server.py
云端会注入 PORT 环境变量，server.py 自动读取并绑定 0.0.0.0。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import main  # noqa: E402

if __name__ == "__main__":
    main()
