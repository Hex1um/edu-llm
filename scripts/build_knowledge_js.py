"""把 data/knowledge_graph.json 同步为 app/knowledge.js。

原因：直接用 file:// 打开 index.html 时，fetch('./data/*.json') 会被浏览器 CORS 拦截。
所以运行时数据以 JS 常量内联，JSON 文件保留给外部工具/脚本消费。

用法：python scripts/build_knowledge_js.py
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
src = root / "data" / "knowledge_graph.json"
dst = root / "app" / "knowledge.js"

data = json.loads(src.read_text(encoding="utf-8"))
dst.write_text(
    "/* AUTO-GENERATED from data/knowledge_graph.json - do not edit by hand */\n"
    "window.KG = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
    encoding="utf-8",
)
print(f"OK: {dst.relative_to(root)}  nodes={len(data['nodes'])}")
