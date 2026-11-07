"""按近五年高考命题趋势生成章节分层练习题骨架。

设计依据见 data/exam_trends.json：
  - 每章 5 题，按分值权重 2.5 + 2.5 + 1.5 + 1.5 + 2 = 10，对应基础:中档:高区分度 = 5:3:2
  - 覆盖 7 类题型：新定义 / 结构不良 / 多选 / 情境建模 / 跨章节 / 存在性 / 递进设问
  - 每题标注 level、weight、knobs（5 个难度旋钮）、trend_tags、rubric（评分要点）
  - 题目全部由本项目自生成，标注 auto_generated=true 与「建议教师审核」

注意：这里的题目是**结构化探究骨架**，用章节概念与核心关系生成，不是具体数值计算题。
有具体数学内容的高区分度题见 data/original_exam_questions.json（原创、手工校订）。
"""
from collections import Counter

# 7 类题型，与 data/exam_trends.json 的 item_types 一一对应
TYPE_LABELS = {
    "concept_check": "概念辨析",
    "condition_open": "条件应用 / 条件开放",
    "new_definition": "新定义题",
    "ill_structured": "结构不良 / 条件开放题",
    "multi_choice": "多选题",
    "modeling": "情境化数学建模",
    "cross_chapter": "跨章节综合",
    "existence": "存在性 / 探究题",
    "graded": "递进设问（压轴三问）",
}
ROTATING = ["new_definition", "ill_structured", "modeling",
            "cross_chapter", "existence", "graded", "multi_choice"]

KNOBS = {"novelty": 0, "openness": 0, "modules": 0, "chain": 0, "construction": 0}


def _knobs(**kw):
    d = dict(KNOBS)
    d.update(kw)
    return d


def _q(n, seq, idx, qtype, level, difficulty, weight, tags, knobs,
       text, answer, analysis, rubric, options=None, subquestions=None):
    item = {
        "id": f"{n['id']}-q{idx}",
        "type": qtype,
        "type_label": TYPE_LABELS[qtype],
        "level": level,
        "difficulty": difficulty,
        "weight": weight,
        "knobs": knobs,
        "trend_tags": tags,
        "q": text,
        "a": answer,
        "analysis": analysis,
        "rubric": rubric,
        "auto_generated": True,
        "author": "本项目自生成",
        "review": "自生成骨架题，建议教师审核后使用",
        "source": "self-authored",
        "license": "self-authored",
    }
    if options:
        item["options"] = options
    if subquestions:
        item["subquestions"] = subquestions
    return item


def _concept(n, seq, idx):
    c1, c2, c3 = n["concepts"]
    f, pit = n["formula"], n["pitfall"]
    return _q(
        n, seq, idx, "concept_check", "基础", 1, 2.5,
        ["前提意识", "反套路"], _knobs(chain=1),
        f"在「{n['name']}」中，有同学直接套用 {f}，做法是：{pit}。\n"
        "请完成三步：(1) 指出该做法错在哪一步；(2) 写出使用这条核心关系之前必须核对的两个前提；"
        "(3) 描述一个会使该结论失效的情形（说明它破坏了哪一条前提即可，不必给出具体数值）。",
        f"错在跳过前提核对。使用 {f} 前需确认 {c1} 与 {c2} 满足相应条件，并检查边界情形。",
        f"{n['why']}。本章围绕 {c1}、{c2}、{c3} 展开，{f} 只在前提成立时可用。"
        f"「{pit}」正是忽略前提或混淆对象层级的典型表现。"
        "自检方法：拿到题目先把条件逐条写下来，逐条确认后再代入结论；"
        "把「结论成立的前提」和「结论描述的对象」分开写，能避免大多数这类失分。",
        ["(1) 1.5 分：明确指出跳过了前提核对。",
         "(2) 1 分：写出两个与本章概念对应的前提。",
         f"(3) 0.5 分：给出破坏 {c1} 或 {c2} 的情形说明。"],
        subquestions=[
            "(1) 指出该做法错在哪一步。",
            "(2) 写出使用核心关系前必须核对的两个前提。",
            "(3) 描述一个使结论失效的情形，说明它破坏了哪条前提。",
        ])


def _condition(n, seq, idx):
    c1, c2, c3 = n["concepts"]
    f = n["formula"]
    return _q(
        n, seq, idx, "condition_open", "基础", 2, 2.5,
        ["条件开放", "前提意识"], _knobs(openness=2, chain=2),
        f"本章核心关系是 {f}。现在把它的一个前提去掉，结论会怎样？\n"
        "请按三步作答，并在每一步前写明你删去 / 补回的是哪一个条件。",
        f"去掉任一前提后，{f} 通常不再无条件成立：要么结论变弱，要么需要补充修正项，"
        f"要么完全失效。补回 {c2} 与边界条件后可重新成立。",
        f"前提由 {c1} 与 {c2} 共同给出。判断「去掉一个前提会怎样」的通用做法是："
        f"先找出结论中最依赖该前提的一步，再看 {c3} 是否仍能推出。"
        "这也是「条件开放」题的判分点：不写明自己删改了哪个条件，后续推导无法复现，即使结论对也不给满分。",
        ["(1) 1 分：列出本章核心关系依赖的全部前提。",
         "(2) 1 分：写明删去的具体前提，并判断结论变弱 / 需修正 / 失效。",
         "(3) 0.5 分：补回一个附加条件并说明它如何恢复结论。"],
        subquestions=[
            "(1) 写出核心关系成立所依赖的全部前提。",
            "(2) 任选一个前提删去，说明结论会怎样变化。",
            "(3) 补上一个你设定的附加条件，使结论在新条件下重新成立。",
        ])


def _multi(n, seq, idx):
    c1, c2, c3 = n["concepts"]
    f = n["formula"]
    correct = [
        f"使用 {f} 之前，需要先核对 {c1} 与 {c2} 所限定的前提",
        f"{n['why']}；因此 {c3} 是本章结论的适用对象，不能替代前提本身",
    ]
    wrong = [
        f"只要题面出现 {c3}，就可以无条件套用 {f}",
        f"「{n['pitfall']}」只是书写细节，不影响结论是否成立",
    ]
    # 4 种正误分布，避免所有章节的答案字母都一样
    patterns = [
        [0, 1, 0, 1],  # C W W C -> A D
        [1, 0, 0, 1],  # W C C W -> B C
        [0, 0, 1, 1],  # C C W W -> A B
        [1, 1, 0, 0],  # W W C C -> C D
    ]
    pat = patterns[seq % len(patterns)]
    opts, letters = [], []
    ci = wi = 0
    for pos, flag in enumerate(pat):
        if flag:
            opts.append(f"{'ABCD'[pos]}. {correct[ci]}"); ci += 1; letters.append('ABCD'[pos])
        else:
            opts.append(f"{'ABCD'[pos]}. {wrong[wi]}"); wi += 1
    ans = "、".join(letters)
    return _q(
        n, seq, idx, "multi_choice", "中档", 3, 1.5,
        ["多选题", "逐项辨析", "部分得分"], _knobs(chain=2, modules=1),
        f"关于「{n['name']}」，下列判断正确的是（多选；全部选对得满分，部分选对得部分分，含错选不得分）。",
        ans,
        "逐项判断：\n" + "\n".join(
            f"{o[:2]} {'正确' if pat[i] else '错误'}：{o[3:]}" for i, o in enumerate(opts)) +
        f"\n两条正确选项共同指向同一件事：{f} 的成立依赖前提，而不是依赖题面里出现了哪个名词。"
        "两个错误选项分别对应「见关键词就套公式」和「把易错点当成无关细节」，"
        "这正是多选题在高分段拉开差距的地方——必须逐项给出理由，不能只凭印象勾选。",
        ["四个选项各 0.375 分：判断正确且写出理由才给分，只勾对字母不写理由减半。",
         "含任一错选，本题 0 分（与高考多选题部分得分规则一致）。"],
        options=opts)


def _rotating_item(n, index, seq, idx, qtype, level, difficulty, weight):
    c1, c2, c3 = n["concepts"]
    f, pit = n["formula"], n["pitfall"]
    pre = ", ".join(index[p]["name"] for p in n.get("prerequisites", []) if p in index) or "基础概念"

    if qtype == "new_definition":
        return _q(
            n, seq, idx, qtype, level, difficulty, weight,
            ["新定义即时理解", "反套路", "完备性论证"], _knobs(novelty=3, chain=3, construction=1),
            f"【新定义 · 即时理解】本题临时定义：若一个对象 x 同时满足 {c1} 与 {c2}，"
            f"且 {f} 在 x 上成立，就称 x 为「本章适格对象」。这个定义不来自任何教材。",
            f"(1) 判定清单须同时含 {c1}、{c2} 与结论成立三项。(2) 不适格；"
            f"「{pit}」跳过了前提核对。(3) 需补充 {c1} 到 {c2} 的蕴含关系或边界条件，否则结论只对部分对象成立。",
            "新定义题的判分点是「先复述定义、再使用定义」：第 (1) 问要求把定义拆成可逐条核对的清单，"
            "第 (2) 问考察把易错行为映射回定义，第 (3) 问要求指出若要得到全称结论还缺什么。"
            "不能凭直觉写「显然成立」——缺少补充条件时正确做法是指出不足，而不是硬证。",
            ["(1) 30%：写出完整判定清单。", "(2) 30%：判断不适格并说明跳过了哪条前提。",
             "(3) 40%：指出需补充的蕴含关系或边界条件，并说明省略后结论不完备。"],
            subquestions=[
                "(1) 用自己的话写出「适格」的完整判定清单。",
                f"(2) 判断：采取「{pit}」这一做法得到的结论所涉及的对象是否适格？说明理由。",
                f"(3) 若要证明「所有满足 {c3} 的对象都适格」，还缺什么条件？写出必须补充的一条并说明不能省略的原因。",
            ])

    if qtype == "ill_structured":
        return _q(
            n, seq, idx, qtype, level, difficulty, weight,
            ["结构不良", "条件开放", "答案不唯一"], _knobs(openness=3, chain=2, construction=2),
            f"【条件开放】题干只给出「已知 {c1}，研究 {n['name']}」，条件不完整，答案并不唯一。"
            f"可选补充：① {c2} 成立；② {c3} 成立且 {f} 适用；③ 不补充任何条件，要求结论对所有情形成立。",
            "三条补充对应不同结论空间：① 可在 {c2} 范围内推出 {f}；② 结论成立但适用范围受限；"
            "③ 一般无法推出全称结论，正确作答是明确写「条件不足」。三条答案不同，均可在各自前提下成立。",
            "结构不良题不设唯一标准答案，评分依据是「所选条件 + 该条件下建模 + 推导 + 结论」是否自洽。"
            "先写明所选编号再作答，判卷者才能复现你的推导；直接猜命题人想要哪条规则，会把整题绑死在一个前提上。"
            "第 (3) 条尤其反套路：识别出「条件不足」本身就是满分答案，硬凑一个结论反而失分。",
            ["(1) 20%：写明所选条件编号。", "(2) 40%：在该条件下给出自洽的推导与结论。",
             "(3) 40%：说明另外两条会给出怎样不同的答案，或指出条件不足。"],
            subquestions=[
                "(1) 从三条可选补充中任选一条，写出编号。",
                "(2) 在你选的条件下，能推出什么结论？写出推导链。",
                "(3) 另外两条分别会给出怎样不同的答案？若某条导致条件不足，请明确指出。",
            ])

    if qtype == "modeling":
        return _q(
            n, seq, idx, qtype, level, difficulty, weight,
            ["真实情境", "数据解读", "结论边界"], _knobs(novelty=2, openness=2, modules=2, chain=2),
            f"【情境建模】某实际问题可抽象为：在 {c1} 的约束下，用 {c2} 描述变化，"
            f"目标是判断 {c3} 是否满足 {f}。请自行设定一个具体的实际情境。",
            "开放题：情境只要与三个概念的对应关系自洽即可；必须显式写出模型假设，"
            "并在假设被否定时说明结论需要重新检验或修正，而不是继续套用原结论。",
            "建模题按「建模 / 假设 / 计算 / 解释 / 边界反思」分别给分，"
            "难点通常不在计算，而在把真实情境里的量对应到 {c1}、{c2}、{c3}，"
            "以及承认结论只在假设成立时有效。只给一个数字、不写假设的答卷拿不到高分。",
            ["(1) 30%：情境与变量对应关系清楚。", "(2) 30%：列出三条可检验的模型假设。",
             "(3) 40%：假设被否定时的修正方案与结论边界说明。"],
            subquestions=[
                "(1) 用一句话写出你设定的实际情境，并说明各变量对应哪个概念。",
                "(2) 列出模型成立必须的三条假设。",
                "(3) 若其中一条假设被实测数据否定，结论该如何修正？",
            ])

    if qtype == "cross_chapter":
        return _q(
            n, seq, idx, qtype, level, difficulty, weight,
            ["跨章节综合", "知识链条"], _knobs(modules=3, chain=3),
            f"【跨章节综合】「{n['name']}」的先修内容是 {pre}。请写出一条同时调用两者的推理链。",
            f"先修提供基本概念与工具，本章把它们推广到 {c3}；{f} 可视为先修结论在更一般情形下的形式。"
            "链条中最容易被跳步的是「验证先修结论的前提在本章仍成立」这一步。",
            f"{pre} → {n['name']} 的推进体现在：从 {c1} 扩展到 {c2} 与 {c3}。"
            f"{n['why']} 先修结论在本章依然成立，但形式更一般。"
            "跨模块题的常见失分不是不会用公式，而是把先修结论直接搬到新对象上，"
            "却没有检查它在新情形下是否仍满足原前提。",
            ["(1) 30%：写出先修结论及其前提。", "(2) 40%：说明本章如何推广、形式如何变化。",
             "(3) 30%：指出最易跳步的一环并说明省略后的后果。"],
            subquestions=[
                "(1) 从先修内容中取出一条结论，并写明它成立的前提。",
                f"(2) 说明本章如何把它推广到 {c3}。",
                "(3) 指出链条中哪一步最容易被跳步；若省略，结论会怎样失效？",
            ])

    if qtype == "existence":
        return _q(
            n, seq, idx, qtype, level, difficulty, weight,
            ["存在性", "构造与验证", "反套路"], _knobs(openness=2, chain=3, construction=3),
            f"【存在性探究】问：是否存在一个对象，同时满足 {c1} 与 {c2}，却使 {f} 不成立？",
            "本题的稳妥结论是「条件不足，无法直接判断」：除非题目补充 {c1} 与 {c2} 之间的蕴含关系及边界条件，"
            "否则既不能构造反例，也不能证明不存在。正确作答是明确指出还缺哪一条信息。",
            "存在性题的判分结构是「结论 + 构造或论证」：判断存在要给出实例并验证，"
            "判断不存在要给出反证或判别式论证，判断条件不足要指出缺失信息。"
            "本题刻意设计成第三种，用来对抗「看到问存在就默认存在、硬凑例子」的套路化反应。"
            "只写「存在」或「不存在」而不给依据，均不得分。",
            ["(1) 30%：明确写出三种判断中的一种（本题应为条件不足）。",
             "(2) 40%：给出与该判断匹配的论证或说明。",
             "(3) 30%：指出还需补充的具体信息，并说明为什么它决定结论。"],
            subquestions=[
                "(1) 先写出你的判断：存在 / 不存在 / 条件不足无法判断。",
                "(2) 若判断存在，构造实例并验证；若判断不存在，给出理由；若判断条件不足，说明原因。",
                "(3) 要作出确定判断，还需要补充哪一条信息？为什么它决定结论？",
            ])

    if qtype == "graded":
        return _q(
            n, seq, idx, qtype, level, difficulty, weight,
            ["低起点多层次", "长论证链", "完备性论证", "高落差"], _knobs(chain=4, construction=3, modules=2),
            f"【递进设问】围绕「{n['name']}」三问独立给分，难度逐问抬升。",
            f"(1) {f} 的前提清单见答案要点，属低起点；(2) 把 {c2} 换成更弱条件后，"
            f"结论需附加修正项或缩小适用范围；(3) 除非补充 {c1} 与 {c2} 的蕴含关系，"
            "否则不存在一组更弱条件使结论仍恒成立；论证必须说明已穷尽所有情形。",
            "压轴题的设计原则是「低起点、多层次、高落差」：第 (1) 问让多数学生能动手，"
            "第 (2) 问要求一般化，第 (3) 问要求构造或完备性论证。"
            "分问独立给分意味着只完成前两问也有分，不必因为最后一问卡住而放弃整题。"
            "第 (3) 问的关键词是「完备」：只举一两个例子不算证明。",
            ["(1) 20%：写出核心关系与前提清单。", "(2) 30%：一般化后的修正结论与适用范围。",
             "(3) 50%：存在性结论 + 构造或穷尽性论证，缺论证不给满分。"],
            subquestions=[
                f"(1) 写出 {f}，并逐条列出它的前提（低起点）。",
                f"(2) 若把 {c2} 换成更弱的条件，结论需要怎样修正（一般化）？",
                "(3) 是否存在一组更弱的条件，使修正后的结论仍恒成立？给出构造或证明不存在，并说明论证为何完备。",
            ])

    # multi_choice 作为轮转项时复用多选模板，但换成更高区分度的措辞
    return _multi(n, seq, idx)


def make_questions(n, index, seq):
    """每章 5 题：基础 2 / 中档 2 / 高区分度 1，权重 2.5+2.5+1.5+1.5+2 = 10（5:3:2）。"""
    q1 = _concept(n, seq, 1)
    q2 = _condition(n, seq, 2)
    q3 = _multi(n, seq, 3)
    t4 = ROTATING[(seq + 2) % len(ROTATING)]
    t5 = ROTATING[seq % len(ROTATING)]
    if t5 == "multi_choice":
        t5 = "graded"
    q4 = _rotating_item(n, index, seq, 4, t4, "中档", 3, 1.5)
    q5 = _rotating_item(n, index, seq, 5, t5, "高区分度", 5, 2)
    return [q1, q2, q3, q4, q5]


def attach_original(nodes, original):
    """把原创高区分度题按 chapter_ids 挂到章节；返回挂载次数。"""
    by_chapter = {}
    for q in original.get("questions", []):
        for cid in q.get("chapter_ids", []):
            by_chapter.setdefault(cid, []).append(dict(q))
    mounts = 0
    for n in nodes:
        extra = by_chapter.get(n["id"])
        if extra:
            n["questions"] = list(n.get("questions", [])) + extra
            mounts += len(extra)
    return mounts


def summarize(nodes):
    """统计题型、层级与分值配比，供 knowledge_graph.stats 使用。"""
    levels, types, weight = Counter(), Counter(), Counter()
    for n in nodes:
        for q in n.get("questions", []):
            if q.get("bonus"):
                continue
            levels[q.get("level", "未标注")] += 1
            types[q.get("type_label", "未标注")] += 1
            weight[q.get("level", "未标注")] += q.get("weight", 0)
    total = sum(weight.values()) or 1
    return {
        "by_level": dict(levels),
        "by_type": dict(sorted(types.items())),
        "score_ratio": {k: round(v / total * 10, 1) for k, v in weight.items()},
        "score_total": total,
    }
