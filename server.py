"""单端口 HTTP 服务入口（云端发布 / 本地运行共用）。

- 监听环境变量 PORT（云端注入），未设置时取命令行参数或 8000
- 绑定 0.0.0.0，服务目录固定为 app/（静态资源全部自带 ?v= 版本号）
- 全部响应强制禁用缓存：Cache-Control / Pragma / Expires
- 新增 /api/chat 同源代理：浏览器把模型请求发到本站同域，由服务端转发到
  上游 OpenAI 兼容接口，彻底规避浏览器直接跨域（CORS）导致的「连接失败」。

用法：
    python server.py            # 本地，http://127.0.0.1:8000/
    PORT=3782 python server.py  # 云端沙箱
"""
import json
import os
import sys
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE = Path(__file__).resolve().parent / "app"


def resolve_base(base):
    """把用户填的接口地址归一为 OpenAI 兼容的 chat/completions 完整地址。

    - 已含 /chat/completions：原样使用
    - 以 /v1 结尾：补 /chat/completions
    - 其它（裸域名或带前缀）：补 /v1/chat/completions
    """
    base = (base or "").strip().rstrip("/")
    if not base:
        raise ValueError("接口地址为空")
    if "/chat/completions" in base:
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, *args):
        pass

    def _send_json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path not in ("/api/chat", "/api/v1/chat/completions"):
            self._send_json(404, {"error": "接口不存在"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            cfg = json.loads(raw or b"{}")
        except Exception as e:  # 请求体损坏
            self._send_json(400, {"error": "请求体解析失败：" + str(e)})
            return
        try:
            target = resolve_base(cfg.get("base", ""))
        except Exception as e:  # 接口地址非法
            self._send_json(400, {"error": str(e)})
            return
        payload = json.dumps({
            "model": cfg.get("model", ""),
            "messages": cfg.get("messages", []),
            "temperature": cfg.get("temperature", 0.4),
            "stream": False,
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(target, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + (cfg.get("key", "") or ""))
        try:
            up = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:  # 上游明确报错（401/404/429...）
            body = e.read().decode("utf-8", "replace")[:600]
            self._send_json(e.code, {"error": "上游返回 " + str(e.code) + "：" + body})
            return
        except Exception as e:  # DNS / 超时 / 证书 / 沙箱禁出网
            self._send_json(502, {"error": "无法连接上游模型服务（" + str(e) +
                                 "）。请确认接口地址正确，且部署环境可访问该域名。"})
            return
        ctype = up.headers.get("Content-Type", "application/json")
        data = up.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8000))
    handler = partial(Handler, directory=str(SITE))
    print(f"serving {SITE} on 0.0.0.0:{port} (Cache-Control: no-store, /api/chat proxy enabled)",
          flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()


if __name__ == "__main__":
    main()
