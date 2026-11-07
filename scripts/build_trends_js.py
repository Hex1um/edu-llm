"""把 data/exam_trends.json 同步为 app/trends.js（window.TRENDS）。

与 knowledge.js 同样的理由：避免 file:// 下 fetch JSON 被 CORS 拦截。
用法：python scripts/build_trends_js.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "data" / "exam_trends.json"
dst = ROOT / "app" / "trends.js"

data = json.loads(src.read_text(encoding="utf-8"))
dst.write_text(
    "/* AUTO-GENERATED from data/exam_trends.json - do not edit by hand */\n"
    "window.TRENDS = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
    encoding="utf-8",
)
print(f"OK  {dst.relative_to(ROOT)}  version={data['version']}  types={len(data['item_types'])}")
