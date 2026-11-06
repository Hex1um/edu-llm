"""把用户自己持有的教材 PDF 转成纯文本，供工作台本地导入。

仅做本地转换，不联网、不上传、不批量抓取。
依赖（可选）：pip install pymupdf
用法：python scripts/pdf_to_text.py 教材.pdf [-o 输出.txt]

合规提醒：只对合法持有的文件使用；转换结果不要分发、不要上传公开服务。
"""
import argparse
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    raise SystemExit("缺少依赖：请先执行 pip install pymupdf")


def convert(pdf: Path) -> str:
    doc = fitz.open(pdf)
    parts = []
    for i, page in enumerate(doc, 1):
        text = page.get_text("text").strip()
        if text:
            parts.append(f"[第 {i} 页]\n{text}")
    doc.close()
    return "\n\n".join(parts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()
    out = args.output or args.pdf.with_suffix(".txt")
    text = convert(args.pdf)
    out.write_text(text, encoding="utf-8")
    print(f"OK: {out}  chars={len(text)}  (仅本地，未上传)")
