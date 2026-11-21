"""单端口 HTTP 服务入口（云端发布 / 本地运行共用）。

- 监听环境变量 PORT（云端注入），未设置时取命令行参数或 8000
- 绑定 0.0.0.0，服务目录固定为 app/（静态资源全部自带 ?v= 版本号）
- 全部响应强制禁用缓存：Cache-Control / Pragma / Expires
- /api/chat 同源代理：浏览器把模型请求发到本站同域，由服务端转发到上游，
  彻底规避浏览器跨域（CORS）导致的「连接失败」；且服务端请求不带浏览器
  Origin，不会被 Pollinations 的 Turnstile 人机验证拦截。

模型来源（参考 Hex1um/hallucindriod 的多源策略）：
- source=free（默认）：匿名免费源，无需任何 Key。按 Kilo Gateway →
  Pollinations 顺序尝试，任一成功即返回；全失败返回可读错误。
  * Kilo Gateway：https://api.kilo.ai/api/gateway，模型 kilo-auto/free（自动路由免费模型）
  * Pollinations：https://text.pollinations.ai/openai，模型 openai-fast
- source=custom：用户自填 OpenAI 兼容端点（base/key/model），透传。

隐私提示：免费源的提示词可能被上游服务商记录用于改进服务，请勿粘贴敏感信息、
公司代码或未公开内容；本项目本身不存储任何提问，密钥仅存用户本机。

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

# 匿名免费源清单（顺序 = fallback 优先级）。每项：(标签, base, 模型)
FREE_SOURCES = [
    ("Kilo Gateway · 免费自动路由", "https://api.kilo.ai/api/gateway", "kilo-auto/free"),
    ("Pollinations · 极速", "https://text.pollinations.ai/openai", "openai-fast"),
]
FREE_TIMEOUT = 25   # 单个免费源超时（秒）
CUSTOM_TIMEOUT = 120


def resolve_base(base):
    """归一用户自定义接口地址为 OpenAI 兼容 chat/completions 完整地址。"""
    base = (base or "").strip().rstrip("/")
    if not base:
        raise ValueError("接口地址为空")
    if "/chat/completions" in base:
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _call(target, payload, key=None, timeout=30):
    """向上游发一次 chat/completions，返回 (status, json_dict_or_none, error_str)。"""
    req = urllib.request.Request(target, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        up = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        return e.code, None, "上游返回 " + str(e.code) + "：" + body
    except Exception as e:
        return 502, None, str(e)
    try:
        data = json.loads(up.read().decode("utf-8", "replace"))
    except Exception as e:
        return 502, None, "上游响应解析失败：" + str(e)
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
    if not text:
        return 502, None, "上游返回为空或无 choices"
    return 200, data, None


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, *args):
        pass

    def _send_json(self, code, obj, extra_headers=None):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
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
        except Exception as e:
            self._send_json(400, {"error": "请求体解析失败：" + str(e)})
            return

        source = (cfg.get("source") or "").strip().lower()
        messages = cfg.get("messages", [])
        temperature = cfg.get("temperature", 0.4)
        max_tokens = cfg.get("max_tokens", 1200)

        # 没显式指定 source 时：填了 base 视为自定义，否则默认免费源
        if not source:
            source = "custom" if (cfg.get("base") or "").strip() else "free"

        if source == "custom":
            try:
                target = resolve_base(cfg.get("base", ""))
            except Exception as e:
                self._send_json(400, {"error": str(e)})
                return
            payload = json.dumps({
                "model": cfg.get("model", ""), "messages": messages,
                "temperature": temperature, "stream": False,
            }, ensure_ascii=False).encode("utf-8")
            code, data, err = _call(target, payload, cfg.get("key") or None, CUSTOM_TIMEOUT)
            if err:
                self._send_json(code, {"error": err, "source": "自定义端点"})
                return
            data["_source"] = "自定义端点"
            self._send_json(200, data, {"X-LLM-Source": "custom"})
            return

        if source == "free":
            payload_tpl = {
                "messages": messages, "temperature": temperature,
                "stream": False, "max_tokens": max_tokens,
            }
            errors = []
            for label, base, model in FREE_SOURCES:
                payload = json.dumps(dict(payload_tpl, model=model), ensure_ascii=False).encode("utf-8")
                target = resolve_base(base)
                code, data, err = _call(target, payload, None, FREE_TIMEOUT)
                if err is None:
                    data["_source"] = label
                    data["_model"] = (data.get("model") or model)
                    self._send_json(200, data, {"X-LLM-Source": "free"})
                    return
                errors.append(label + "：" + err)
            self._send_json(502, {
                "error": "免费源均不可用。" + "；".join(errors) +
                         "。可稍后重试，或在模型设置里改用自定义端点。",
                "source": "免费源",
            })
            return

        self._send_json(400, {"error": "未知的模型来源：" + source})


# 兼容旧脚本可能引用的类名
NoStoreHandler = Handler


def main():
    port = int(os.environ.get("PORT") or (sys.argv[1] if len(sys.argv) > 1 else 8000))
    handler = partial(Handler, directory=str(SITE))
    print(f"serving {SITE} on 0.0.0.0:{port} "
          f"(Cache-Control: no-store, /api/chat proxy: free=[kilo,pollinations] + custom)",
          flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()


if __name__ == "__main__":
    main()
