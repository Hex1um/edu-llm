"""把章节骨架总表扩成完整知识库（v0.4.0 命题趋势版）。

输入：
  scripts/curriculum_hs.py              高中数理化章节骨架
  scripts/curriculum_uni.py             大学理工核心课程章节骨架
  scripts/question_bank.py              7 类题型 / 5:3:2 分层的题目生成器
  data/featured_nodes.json              22 个人工精讲章节（深度样板）
  data/original_exam_questions.json     10 道原创高中数学高区分度题
  data/exam_trends.json                 近五年命题趋势与合规调研摘要

输出：
  data/knowledge_graph.json             全量章节节点；每章 5 段加深理解与 5 道分层题
  （再由 build_knowledge_js.py / build_trends_js.py 生成前端内联数据）

合规：所有讲解与题目均由本项目自撰 / 自生成，不含任何教材、教辅、真题或模考卷原文。
自生成题标注 auto_generated=true 与「建议教师审核后使用」。

用法：
  python scripts/build_curriculum.py
  python scripts/build_knowledge_js.py
  python scripts/build_trends_js.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import curriculum_hs  # noqa: E402
import curriculum_uni  # noqa: E402
import question_bank  # noqa: E402

VERSION = "0.4.0"
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

PRACTICE_PLAN = "每章 5 题：基础 2 / 中档 2 / 高区分度 1，按分值 5:3:2；含多选、结构不良与递进设问"


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
        {"title": "命题视角", "text": (
            f"近五年高考与模考不再只考 {n['formula']} 的直接代入，更常见的是把它放进陌生情境、"
            "新定义或跨模块链条里：先要求复述前提，再判断结论在更弱条件下是否仍成立，最后要求构造或完备性论证。"
            "本章练习按分值 5:3:2 分层，含多选题、条件开放题与递进设问；"
            "做高区分度题时先写清所用前提，比急着算出答案更容易得分。")},
    ]


def enrich_featured(n, index, seq):
    """给人工精讲章节补齐统一字段，保留其手写例题，并套用 v0.4.0 分层练习。"""
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
        {"title": "命题视角", "text": (
            "高区分度题常把本章结论藏在陌生表述下，或要求判断结论在更弱条件下是否仍成立。"
            "作答时先复述所用结论的前提，再展开推导；只写答案、不写前提容易在分问给分中丢分。")},
    ]
    ex = n.get("example") or {"q": f"举一个说明 {n['name']} 的例子。", "a": "见本章讲解。"}
    hand = {
        "id": n["id"] + "-example",
        "type": "featured_example", "type_label": "精讲例题", "level": "中档",
        "difficulty": 2, "weight": 2, "bonus": True,
        "knobs": {"novelty": 0, "openness": 0, "modules": 1, "chain": 1, "construction": 0},
        "trend_tags": ["人工精校"],
        "q": ex["q"], "a": ex["a"], "analysis": n.get("summary", ""),
        "rubric": ["写出关键步骤 60%", "结论与定义域 / 前提核对 40%"],
        "auto_generated": False, "author": "本项目自撰",
        "review": "本项目自撰例题", "source": "self-authored", "license": "self-authored",
    }
    n["questions"] = question_bank.make_questions(n, index, seq) + [hand]
    return n


def main():
    hs = parse_rows(curriculum_hs.ROWS, "highschool")
    uni = parse_rows(curriculum_uni.ROWS, "university")
    base_nodes = hs + uni
    index = {n["id"]: n for n in base_nodes}

    for seq, n in enumerate(base_nodes):
        n["summary"] = (
            f"{n['name']}属于{n['book']}{n['unit']}，围绕{n['concepts'][0]}、"
            f"{n['concepts'][1]}与{n['concepts'][2]}展开。{n['why']}"
            f"本章的核心关系是 {n['formula']}，使用时要特别注意：{n['pitfall']}。")
        n["misconceptions"] = [n["pitfall"]]
        n["deep_dive"] = make_deep_dive(n, index)
        n["questions"] = question_bank.make_questions(n, index, seq)
        n["practice_plan"] = PRACTICE_PLAN
        n["source"] = "章节骨架 + 自撰讲解与题目"
        n["license"] = "self-authored"

    featured_raw = json.loads((ROOT / "data" / "featured_nodes.json").read_text(encoding="utf-8"))
    featured = [enrich_featured(x, index, 200 + i) for i, x in enumerate(featured_raw["nodes"])]
    for n in featured:
        n["practice_plan"] = PRACTICE_PLAN
        n["source"] = "精讲专题 + 自撰讲解与题目"
        n["license"] = "self-authored"
    index.update({n["id"]: n for n in featured})

    all_nodes = base_nodes + featured
    original = json.loads((ROOT / "data" / "original_exam_questions.json").read_text(encoding="utf-8"))
    mounts = question_bank.attach_original(all_nodes, original)

    trends = json.loads((ROOT / "data" / "exam_trends.json").read_text(encoding="utf-8"))

    # 先修 id 必须能在库里找到（精讲节点用的是短 id，允许保留原样）
    ids = {n["id"] for n in all_nodes}
    dangling = sorted({p for n in all_nodes for p in n.get("prerequisites", [])
                       if p not in ids and p not in LEGACY_NAMES})

    books = Counter(n["book"] for n in base_nodes)
    stages = Counter(n["stage"] for n in base_nodes)
    subjects = Counter(n["subject"] for n in base_nodes)
    qcount = sum(len(n["questions"]) for n in all_nodes)
    bonus = sum(1 for n in all_nodes for q in n["questions"] if q.get("bonus"))
    dist = question_bank.summarize(all_nodes)

    out = {
        "version": VERSION,
        "generated_at": "2026-11-07",
        "note": (
            "全量章节骨架按通行教材目录整理，仅含书目 / 章节映射与本项目自撰的讲解和题目，"
            "不含任何教材、教辅、真题或模考卷原文。具体册次与章名请以各校用书与出版社目录为准。"),
        "license": "self-authored（本项目自撰内容）；第三方教材书目信息仅作引用",
        "practice_plan": PRACTICE_PLAN,
        "trend_note": trends["trend_research"]["verdict"],
        "question_system": {
            "version": VERSION,
            "chapter_distribution": "基础 5 : 中档 3 : 高区分度 2（按分值，整卷模拟建议 3:5:2）",
            "per_chapter_questions": 5,
            "item_types": [t["name"] for t in trends["item_types"]],
            "difficulty_knobs": [k["name"] for k in trends["difficulty_knobs"]],
            "discrimination_index": trends["distribution"]["discrimination_index"]["formula"],
            "score_ratio": dist["score_ratio"],
        },
        "stats": {
            "textbooks": len(books),
            "chapters": len(base_nodes),
            "featured_chapters": len(featured),
            "total_nodes": len(all_nodes),
            "questions": qcount,
            "chapter_practice_questions": qcount - bonus,
            "bonus_questions": bonus,
            "original_questions": len(original["questions"]),
            "original_mounts": mounts,
            "highschool_chapters": stages["highschool"],
            "university_chapters": stages["university"],
            "subjects": len(subjects),
            "questions_by_level": dist["by_level"],
            "questions_by_type": dist["by_type"],
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
    print(f"    分层练习 {qcount - bonus} 道 | 附加题 {bonus} 道（原创 {len(original['questions'])} 道挂载 {mounts} 次 + 精讲例题 {len(featured)} 道）")
    print(f"    分值配比: {dist['score_ratio']} | 层级: {dist['by_level']}")
    print(f"    悬空先修引用: {dangling or '无'}")


if __name__ == "__main__":
    main()
