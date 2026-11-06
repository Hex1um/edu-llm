"""单端口 HTTP 服务入口（云端发布 / 本地运行共用）。

- 监听环境变量 PORT（云端注入），未设置时取命令行参数或 8000
- 绑定 0.0.0.0，服务目录固定为 app/（静态资源全部自带 ?v= 版本号）
- 全部响应强制禁用缓存：Cache-Control / Pragma / Expires

用法：
    python server.py            # 本地，http://127.0.0.1:8000/
    PORT=3782 python server.py  # 云端沙箱
"""
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE = Path(__file__).resolve().parent / "app"


class NoStoreHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8000))
    handler = partial(NoStoreHandler, directory=str(SITE))
    print(f"serving {SITE} on 0.0.0.0:{port} (Cache-Control: no-store)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()


if __name__ == "__main__":
    main()
