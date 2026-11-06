"""把章节骨架总表扩成完整知识库。

输入：
  scripts/curriculum_hs.py      高中数理化章节骨架
  scripts/curriculum_uni.py     大学理工核心课程章节骨架
  data/featured_nodes.json      22 个人工精讲章节（深度样板）

输出：
  data/knowledge_graph.json     全量章节节点；每章含 deep_dive 四段讲解与 3 道自生成题

所有讲解与题目均由本项目自撰/自生成，不含任何教材或教辅原文。
自生成题目标注 auto_generated=true，建议教师审核后使用。

用法：python scripts/build_curriculum.py && python scripts/build_knowledge_js.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import curriculum_hs  # noqa: E402
import curriculum_uni  # noqa: E402

VERSION = "0.2.0"
FIELDS = 13

# 精讲专题沿用的旧版短 id → 中文名（仅用于显示先修关系，不参与检索）
LEGACY_NAMES = {
    "hs-math-function": "函数与映射", "hs-math-derivative": "导数及其应用",
    "hs-math-trig": "三角函数与恒等变换", "hs-math-sequence": "数列与数学归纳法",
    "hs-math-conic": "圆锥曲线", "hs-math-prob": "概率与统计",
    "hs-phy-newton": "牛顿运动定律", "hs-phy-energy": "功、能与机械能守恒",
    "hs-phy-electric": "电场与电路", "hs-phy-induction": "电磁感应",
    "hs-chem-mole": "物质的量", "hs-chem-redox": "氧化还原反应",
    "hs-chem-equilibrium": "化学平衡", "hs-chem-organic": "有机化学基础",
    "uni-math-limit": "极限与连续", "uni-math-integral": "一元函数积分学",
    "uni-linalg-rank": "矩阵、行列式与秩", "uni-linalg-eigen": "特征值",
    "uni-prob-dist": "随机变量与常见分布", "uni-phy-em": "电磁场与麦克斯韦方程组",
    "uni-cs-complexity": "算法复杂度与数据结构", "uni-cs-memory": "指针、内存与程序运行时",
}


def parse_rows(raw, stage):
    nodes, seen = [], set()
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != FIELDS:
            raise ValueError(f"字段数应为 {FIELDS}，实际 {len(parts)}：{line[:80]}")
        (nid, subject, book, unit, name, c1, c2, c3,
         formula, why, pitfall, prereq_raw, diff) = parts
        if nid in seen:
            raise ValueError(f"重复 id: {nid}")
        seen.add(nid)
        concepts = [c1, c2, c3]
        prereq = [x for x in prereq_raw.split(",") if x] if prereq_raw else []
        nodes.append({
            "id": nid, "name": name, "stage": stage, "subject": subject,
            "book": book, "unit": unit, "chapter": f"{book} {unit} {name}",
            "concepts": concepts, "formula": formula, "why": why, "pitfall": pitfall,
            "prerequisites": prereq, "difficulty": int(diff),
            "featured": False,
        })
    return nodes


def pre_names(pre, index):
    out = []
    for p in pre:
        if p in index:
            out.append(index[p]["name"])
        elif p in LEGACY_NAMES:
            out.append(LEGACY_NAMES[p])
    return out


def make_deep_dive(n, index):
    c1, c2, c3 = n["concepts"]
    pre = pre_names(n["prerequisites"], index)
    link = "、".join(pre) if pre else "本章所需的预备概念"
    return [
        {"title": "本质直觉", "text": n["why"] + " 抓住这一条，本章的公式和结论就不再是需要死记的孤立条目。"},
        {"title": "概念边界", "text": (
            f"本章以 {c1}、{c2}、{c3} 为骨架。核心关系是 {n['formula']}，"
            "但它有明确的适用前提；超出前提外推是本章最常见的失分点。"
            "做题时先把前提逐条写下来，再决定是否可以使用该结论。")},
        {"title": "常见卡点", "text": (
            f"{n['pitfall']}。自检方法：拿到题目先圈出条件，检查是否真的满足结论的前提，"
            f"再确认 {c1} 与 {c2} 是否被放在了同一个层次上讨论。")},
        {"title": "向上连接", "text": (
            f"先修：{link}。往前看，{c3} 会在后续章节里被推广到更一般的情形，"
            f"届时 {c1} 只是一个特例。把本章放进这条链条里理解，比孤立背公式更牢。")},
    ]


def make_questions(n, index):
    c1, c2, c3 = n["concepts"]
    pre = pre_names(n["prerequisites"], index)
    link = "、".join(pre) if pre else "基础的数学与科学概念"
    base = {"auto_generated": True, "review": "自生成题目，建议教师审核后使用"}
    q1 = {
        **base, "type": "概念辨析", "difficulty": 1,
        "q": f"有同学在做题时采取了这样的做法：{n['pitfall']}。请判断该做法是否正确，并说明理由。",
        "a": "该做法不正确。",
        "analysis": (
            f"{n['why']}。本章围绕 {c1}、{c2}、{c3} 展开，"
            f"{n['formula']} 只在相应前提下成立。"
            f"上述做法正是忽略前提或混淆对象层级导致的典型错误；"
            f"正确做法是先确认 {c1} 的适用条件，再套用结论。"),
    }
    q2 = {
        **base, "type": "条件应用", "difficulty": 2,
        "q": f"写出本章的核心关系「{n['formula']}」，说明它成立需要哪些前提；若去掉其中一个前提，结论会怎样变化？",
        "a": n["formula"],
        "analysis": (
            f"前提由 {c1} 与 {c2} 给出。去掉任一前提后，原结论通常需要额外修正甚至完全不成立；"
            f"这也是「{n['pitfall']}」之所以成为高频错因的原因。"
            "解题时建议先列前提清单，再代入数值或推导。"),
    }
    if pre:
        q3 = {
            **base, "type": "跨章联系", "difficulty": 3,
            "q": f"本章「{n['name']}」与先修内容「{link}」如何衔接？举一个需要同时用到两者的具体场景。",
            "a": f"先修提供基本概念与工具，本章把它们推广到 {c3}。",
            "analysis": (
                f"{link} → {n['name']} 的推进体现在：从 {c1} 扩展到 {c2} 与 {c3}。"
                f"{n['why']} 先修中的结论在本章依然成立，但形式更一般。"
                "若能举出同时调用两者的例题，说明知识链条已经打通。"),
        }
    else:
        q3 = {
            **base, "type": "跨章联系", "difficulty": 3,
            "q": f"本章「{n['name']}」在整门课程中处于什么位置？举一个后续章节或工程场景会用到 {c3} 的例子。",
            "a": f"{n['name']} 是后续内容的基础模块。",
            "analysis": (
                f"本章建立 {c1}、{c2}、{c3} 三个基本概念与 {n['formula']}，"
                "后续章节通常会在更弱的假设或更高维的情形下重新使用它。"
                "这类起点章节要建立的是语言与前提意识，而不只是结论本身。"),
        }
    return [q1, q2, q3]


def enrich_featured(n, index):
    """给人工精讲章节补齐统一字段，保留其手写例题。"""
    pre = n.get("prerequisites", [])
    pre_txt = "、".join(pre_names(pre, index)) or "基础概念"
    concepts = [n["name"]] + (n.get("misconceptions") or [])[:2]
    while len(concepts) < 3:
        concepts.append(n["subject"])
    n = dict(n)
    n.update({
        "book": "精讲专题（人工精校）",
        "unit": "精讲",
        "chapter": n.get("chapter", n["name"]),
        "concepts": concepts[:3],
        "formula": n.get("formula", ""),
        "why": n.get("summary", "")[:60],
        "pitfall": (n.get("misconceptions") or ["忽略结论成立的前提"])[0],
        "featured": True,
    })
    n["deep_dive"] = [
        {"title": "本质直觉", "text": n.get("summary", "")},
        {"title": "概念边界", "text": f"核心关系：{n['formula']}。先修：{pre_txt}。使用结论前先核对前提。"},
        {"title": "常见卡点", "text": "；".join(n.get("misconceptions") or [])},
        {"title": "向上连接", "text": f"与 {pre_txt} 衔接；本章为同一学科后续章节提供基础。"},
    ]
    ex = n.get("example") or {"q": f"举一个说明 {n['name']} 的例子。", "a": "见本章讲解。"}
    qs = [{
        "type": "精讲例题", "difficulty": 2, "auto_generated": False,
        "review": "本项目自撰例题", "q": ex["q"], "a": ex["a"],
        "analysis": n.get("summary", ""),
    }]
    qs.append({
        "type": "概念辨析", "difficulty": 1, "auto_generated": True,
        "review": "自生成题目，建议教师审核后使用",
        "q": f"有同学在做题时采取了这样的做法：{n['pitfall']}。请判断并说明理由。",
        "a": "该做法不正确。",
        "analysis": "；".join(n.get("misconceptions") or []) + "。请先写出结论前提再判断。",
    })
    qs.append({
        "type": "跨章联系", "difficulty": 3, "auto_generated": True,
        "review": "自生成题目，建议教师审核后使用",
        "q": f"{n['name']} 与先修内容 {pre_txt} 的关系是什么？举一个同时用到两者的场景。",
        "a": "先修提供工具，本章在此基础上给出新的结论。",
        "analysis": f"核心关系 {n['formula']} 可视为先修结论在更一般情形下的推广。",
    })
    n["questions"] = qs
    return n


def main():
    hs = parse_rows(curriculum_hs.ROWS, "highschool")
    uni = parse_rows(curriculum_uni.ROWS, "university")
    base_nodes = hs + uni
    index = {n["id"]: n for n in base_nodes}

    for n in base_nodes:
        n["summary"] = (
            f"{n['name']}属于{n['book']}{n['unit']}，围绕{n['concepts'][0]}、"
            f"{n['concepts'][1]}与{n['concepts'][2]}展开。{n['why']}"
            f"本章的核心关系是 {n['formula']}，使用时要特别注意：{n['pitfall']}。")
        n["misconceptions"] = [n["pitfall"]]
        n["deep_dive"] = make_deep_dive(n, index)
        n["questions"] = make_questions(n, index)
        n["source"] = "章节骨架 + 自撰讲解与题目"
        n["license"] = "self-authored"

    featured_raw = json.loads((ROOT / "data" / "featured_nodes.json").read_text(encoding="utf-8"))
    featured = [enrich_featured(x, index) for x in featured_raw["nodes"]]
    index.update({n["id"]: n for n in featured})

    # 先修 id 必须能在库里找到（精讲节点用的是短 id，允许保留原样）
    all_nodes = base_nodes + featured
    ids = {n["id"] for n in all_nodes}
    dangling = sorted({p for n in all_nodes for p in n.get("prerequisites", [])
                       if p not in ids and p not in LEGACY_NAMES})

    books = Counter(n["book"] for n in base_nodes)
    stages = Counter(n["stage"] for n in base_nodes)
    subjects = Counter(n["subject"] for n in base_nodes)
    qcount = sum(len(n["questions"]) for n in all_nodes)

    out = {
        "version": VERSION,
        "generated_at": "2026-11-07",
        "note": (
            "全量章节骨架按通行教材目录整理，仅含书目/章节映射与本项目自撰的讲解和题目，"
            "不含任何教材或教辅原文。具体册次与章名请以各校用书与出版社目录为准。"),
        "license": "self-authored（本项目自撰内容）；第三方教材书目信息仅作引用",
        "stats": {
            "textbooks": len(books),
            "chapters": len(base_nodes),
            "featured_chapters": len(featured),
            "total_nodes": len(all_nodes),
            "questions": qcount,
            "highschool_chapters": stages["highschool"],
            "university_chapters": stages["university"],
            "subjects": len(subjects),
        },
        "books": [
            {"book": b, "count": c,
             "stage": next(n["stage"] for n in base_nodes if n["book"] == b),
             "subject": next(n["subject"] for n in base_nodes if n["book"] == b)}
            for b, c in sorted(books.items())
        ],
        "dangling_prerequisites": dangling,
        "nodes": all_nodes,
    }
    dest = ROOT / "data" / "knowledge_graph.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK  {dest.relative_to(ROOT)}")
    print(f"    教材 {len(books)} 种 | 章节 {len(base_nodes)} 章（高中 {stages['highschool']} / 大学 {stages['university']}）")
    print(f"    学科 {len(subjects)} 类 | 精讲 {len(featured)} 章 | 节点 {len(all_nodes)} | 题目 {qcount} 道")
    print(f"    悬空先修引用: {dangling or '无'}")


if __name__ == "__main__":
    main()
