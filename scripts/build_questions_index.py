"""把全部题目（原创 + 分层练习 + 精讲例题）按「教材 → 章节」重新归类，产出：

- data/questions_by_chapter.json  （完整、机器可读，含每题全部字段）
- questions_by_chapter.md        （人工可读：每章紧凑表格 + 十道原创题完整版）

说明：本项目不含任何第三方真题 / 模考卷 / 教辅原题；所有题目均为原创或自生成，
按合规边界只沉淀方法论与自撰内容。详见 README 第 3、11、12 节。

用法：python scripts/build_questions_index.py
"""
import json
from pathlib import Path
from collections import Counter, OrderedDict

ROOT = Path(__file__).resolve().parent.parent
kg = json.loads((ROOT / "data" / "knowledge_graph.json").read_text(encoding="utf-8"))
originals = json.loads((ROOT / "data" / "original_exam_questions.json").read_text(encoding="utf-8"))["questions"]

nodes = kg["nodes"]

# ---- 统计 ----
levels = Counter(); types = Counter(); sources = Counter(); total = 0
for n in nodes:
    for q in n.get("questions", []):
        total += 1
        levels[q.get("level", "?")] += 1
        types[q.get("type_label") or q.get("type", "?")] += 1
        sources["原创(bonus)" if q.get("bonus") else ("精讲例题" if n.get("featured") else "分层练习")] += 1

# ---- 按教材分组（保持 KG 节点顺序）----
books = OrderedDict()
for n in nodes:
    b = n.get("book", "其他")
    books.setdefault(b, []).append(n)

def src_of(n, q):
    if q.get("bonus"):
        return "原创"
    return "精讲" if n.get("featured") else "分层"

def trunc(s, n=78):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"

# ---- 构建 JSON ----
out_books = []
for b, ns in books.items():
    chs = []
    for n in ns:
        qs = n.get("questions", [])
        if not qs:
            continue
        chs.append({
            "id": n["id"], "unit": n.get("unit", ""), "name": n.get("name", ""),
            "difficulty": n.get("difficulty", 2), "question_count": len(qs),
            "questions": qs,
        })
    if chs:
        out_books.append({
            "book": b, "stage": ns[0].get("stage", ""), "subject": ns[0].get("subject", ""),
            "chapter_count": len(chs),
            "question_count": sum(c["question_count"] for c in chs),
            "chapters": chs,
        })

index = OrderedDict()
index["generated_at"] = "2026-11-07"
index["disclaimer"] = "不含任何第三方真题/模考卷/教辅原题；均为原创或自生成，详见 README。"
index["total"] = total
index["by_level"] = dict(levels)
index["by_type"] = dict(types)
index["by_source"] = dict(sources)
index["books"] = out_books
(ROOT / "data" / "questions_by_chapter.json").write_text(
    json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

# ---- 构建 Markdown ----
L = []
L.append("# 全部题目按章节分类索引（v0.4.0）\n")
L.append("> **合规声明**：本索引不含任何第三方真题、模考卷或教辅原题题干/答案/解析。"
         "所有题目均为本项目**原创**或按章节概念**自生成**，按合规边界只沉淀方法论与自撰内容。\n")
L.append(f"> 合计 **{total}** 道题，分布在 **{len(books)}** 种教材 / **{sum(1 for b in books.values() for n in b if n.get('questions'))}** 个章节。\n")
L.append("## 总体分布\n")
L.append("- 按层级：" + "，".join(f"{k} {v}" for k, v in levels.most_common()) + "\n")
L.append("- 按题型：" + "，".join(f"{k} {v}" for k, v in types.most_common()) + "\n")
L.append("- 按来源：" + "，".join(f"{k} {v}" for k, v in sources.most_common()) + "\n")

for b, ns in books.items():
    stage = ns[0].get("stage", ""); subj = ns[0].get("subject", "")
    chs = [n for n in ns if n.get("questions")]
    L.append(f"\n## {b}（{'高中' if stage=='highschool' else '大学' if stage=='university' else '精讲'} · {subj} · {len(chs)} 章 · {sum(len(n['questions']) for n in chs)} 题）\n")
    for n in chs:
        qs = n["questions"]
        L.append(f"### {n.get('unit','')} {n.get('name','')} （{n['id']} · 难度 {n.get('difficulty',2)} · {len(qs)} 题）\n")
        L.append("| # | 题型 | 层级 | 难度 | 分值 | 题干 | 来源 |")
        L.append("|---|---|---|---|---|---|---|")
        for i, q in enumerate(qs, 1):
            L.append(f"| {i} | {q.get('type_label') or q.get('type','')} | {q.get('level','')} | {q.get('difficulty',2)} | {q.get('weight',0)} | {trunc(q.get('q',''))} | {src_of(n,q)} |")
        L.append("")

# 十道原创题完整版
L.append("\n---\n\n## 十道原创高区分度题（完整版，建议教师审核）\n")
L.append("> 以下题目为原创，无第三方原题；按近五年命题趋势设计（新定义 / 多选 / 结构不良 / 建模 / 存在性 / 递进设问）。\n")
for q in originals:
    L.append(f"### {q['id']} · {q['type_label']} · {q['level']} · 难度 {q['difficulty']} · {q['weight']} 分\n")
    L.append(f"- 挂载章节：{', '.join(q.get('chapter_ids', []))}")
    L.append(f"- 趋势标签：{', '.join(q.get('trend_tags', []))}\n")
    L.append("**题干**\n\n" + q["q"] + "\n")
    if q.get("options"):
        L.append("\n**选项**\n")
        for o in q["options"]:
            L.append(f"- {o}")
        L.append("")
    if q.get("subquestions"):
        L.append("\n**分问**\n")
        for s in q["subquestions"]:
            L.append(f"- {s}")
        L.append("")
    L.append("**答案**\n\n" + q["a"] + "\n")
    L.append("**解析**\n\n" + q["analysis"] + "\n")
    if q.get("rubric"):
        L.append("\n**评分要点**\n")
        for r in q["rubric"]:
            L.append(f"- {r}")
        L.append("")

md = "\n".join(L)
(ROOT / "questions_by_chapter.md").write_text(md, encoding="utf-8")
print(f"OK  data/questions_by_chapter.json  总题 {total} / 教材 {len(books)} 种")
print(f"OK  questions_by_chapter.md         {len(md)//1024} KB")
