"""把 data/official_channels.json 同步为 app/official.js（window.OFFICIAL）。

与 knowledge.js / trends.js 同样理由：file:// 下 fetch JSON 被 CORS 拦截。
用法：python scripts/build_official_js.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data = json.loads((ROOT / "data" / "official_channels.json").read_text(encoding="utf-8"))
dst = ROOT / "app" / "official.js"
dst.write_text(
    "/* AUTO-GENERATED from data/official_channels.json - do not edit by hand */\n"
    "window.OFFICIAL = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
    encoding="utf-8",
)
print(f"OK  {dst.relative_to(ROOT)}  channels={len(data['channels'])}")
