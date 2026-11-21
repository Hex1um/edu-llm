"""把用户自己从官方渠道（如国家中小学智慧教育平台）下载的 Word(.docx)
题目文档转成纯文本，供工作台本地导入。

零依赖：docx 本质是一个 zip 包，正文在 word/document.xml；用标准库
zipfile + xml.etree 提取段落文本即可，不需要 python-docx。
不联网、不上传、不批量抓取。

合规性：只对用户自己合法持有 / 从官方渠道按条款下载的文档使用；
平台声明「免费使用，任何单位及个人不得用于商业行为」，转换结果
仅供本人本地学习，不要分发或上传公开服务。

用法：
    python scripts/docx_to_text.py 试卷.docx [-o 输出.txt]
也可与 pdf_to_text.py 一起用于「官方渠道自助导题 → 本地导入」流程。
"""
import argparse
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def docx_to_text(docx: Path) -> str:
    if not zipfile.is_zipfile(docx):
        raise ValueError("不是有效的 .docx（不是 zip 包）")
    with zipfile.ZipFile(docx) as z:
        names = set(z.namelist())
        if "word/document.xml" not in names:
            raise ValueError("docx 中缺少 word/document.xml")
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    lines = []
    # 遍历所有段落（含表格单元格内的段落），按文档顺序拼接
    for p in root.iter(W + "p"):
        parts = [t.text or "" for t in p.iter(W + "t")]
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return "\n\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("docx", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    args = ap.parse_args()
    out = args.output or args.docx.with_suffix(".txt")
    text = docx_to_text(args.docx)
    out.write_text(text, encoding="utf-8")
    print(f"OK: {out}  chars={len(text)}  (仅本地，未上传)")
