/* 学序 v0.4.0 — DeepSeek 风格教材锚定辅导工作台
   设计参考：OmniEdu（教学指令分类、课程锚定、错因诊断）
             DeepTutor（可溯源 RAG、版本化来源、错题与掌握度）
   命题依据：data/exam_trends.json（近五年趋势调研摘要，不转载试卷原文）
   合规：不内置任何教材 / 教辅 / 真题原文；全文仅来自用户本地导入，不上传、不分发。
   网络：模型请求经本站 /api/chat 同源代理转发，规避浏览器跨域（CORS）导致的连接失败。 */
(function () {
  'use strict';

  var KG = window.KG || { nodes: [] };
  var TRENDS = window.TRENDS || {};
  var VERSION = '0.4.0';
  var LS_API = 'xuexu.api';
  var LS_WRONG = 'xuexu.wrongbook';

  var MODES = [
    { id: 'solve', name: '直接解题', desc: '完整步骤与答案',
      prompt: '你是面向中国高中与大学理工科学生的学科辅导老师。请依据【知识库片段】完整求解题目：写出关键步骤、所用公式与最终答案。每个结论后用 [编号] 标注依据的片段。片段不足时明确说明，不得编造教材原文。' },
    { id: 'hint', name: '分步提示', desc: '不直接给答案（支架式）',
      prompt: '你是采用支架式教学的辅导老师。禁止直接给出最终答案。请把问题拆成 2~4 个渐进提示，每个提示只推进一小步，最后给一个引导性问题让学生自己完成。依据【知识库片段】，用 [编号] 标注。' },
    { id: 'diagnose', name: '错因诊断', desc: '依据学生作答定位卡点',
      prompt: '你是学习诊断专家。必须依据学生实际写出的作答来定位出错步骤、判断 misconception 类型、指出缺失的先修知识点，并给出补救建议。禁止仅凭题目猜测。结合【知识库片段】的「常见错误」与「先修关系」，用 [编号] 标注依据；若学生未提供作答，先要求其提供。' },
    { id: 'socratic', name: '苏格拉底追问', desc: '用问题推动推理',
      prompt: '你是苏格拉底式辅导者。不要讲解、不要给答案，只用一个接一个的问题引导学生自己发现关键关系。每轮最多提 2 个问题，问题要具体、可回答，并依据【知识库片段】（用 [编号] 标注）。' },
    { id: 'explain', name: '概念讲解', desc: '锚定章节与先修',
      prompt: '你是课程讲解老师。请锚定【知识库片段】中的教材章节，先说明该知识点的先修基础，再用直觉解释核心概念，接着给一个最小例子，最后列出 2~3 个常见误区。用 [编号] 标注依据，不得扩写片段之外的教材原文。' },
    { id: 'quiz', name: '生成练习', desc: '出题 + 答案 + 解析',
      prompt: '你是命题老师。依据【知识库片段】生成 2 道由易到难的题目，附标准答案与逐条解析，并标注每题考查的知识点与教材章节。用 [编号] 标注依据。题目须自撰，不得复制任何教辅、真题或模考原题；优先使用新定义、条件开放、多选、递进设问等题型，并写明评分要点。' }
  ];

  var PRESETS = {
    deepseek: { base: 'https://api.deepseek.com', model: 'deepseek-chat' },
    openai: { base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
    openrouter: { base: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o-mini' },
    moonshot: { base: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' }
  };

  /* B 级开放语料：许可标签决定能否进入产品化训练/服务 */
  var OPEN_SOURCES = [
    { name: 'opendatalab/K12textbook', license: 'Apache-2.0（原教材版权另计）', nc: true },
    { name: 'GAOKAO-Bench', license: '试题版权另计，研究用途', nc: true },
    { name: 'CJEval', license: '仅学术研究，禁商用', nc: true },
    { name: 'C-Eval / CMMLU', license: 'CC BY-NC-SA 4.0，禁商用', nc: true },
    { name: 'CMATH', license: 'CC BY 4.0，可商用需署名', nc: false },
    { name: 'OmniEdu 训练数据集', license: '按数据集卡与上游来源核对', nc: true }
  ];

  var state = {
    mode: 'solve', stage: 'all', subject: 'all',
    api: null, docs: [], imported: [], hits: [],
    history: [], wrong: [], busy: false,
    activeBook: null, activeChapter: null
  };

  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  }); }
  function readLS(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  function writeLS(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function setStatus(t) { $('statusLine').textContent = t; }

  /* ---------- 文档与检索（中文单字 + bigram，BM25） ---------- */
  function nodeToDoc(n) {
    var dd = (n.deep_dive || []).map(function (x) { return x.title + ' ' + x.text.slice(0, 120); }).join(' ');
    return {
      id: n.id, title: n.name, chapter: n.chapter || '—',
      stage: n.stage, subject: n.subject, node: n,
      source: n.featured ? '精讲专题（人工精校）' : '章节骨架（自撰）', license: 'self-authored',
      text: [n.name, n.book, n.unit, n.chapter, n.summary, n.formula, n.why, n.pitfall,
             (n.concepts || []).join(' '), (n.misconceptions || []).join(' '),
             n.example ? n.example.q + ' ' + n.example.a : '',
             (n.prerequisites || []).join(' '), dd, n.practice_plan || ''].join('\n')
    };
  }
  function tokenize(s) {
    var segs = String(s || '').toLowerCase().match(/[\u4e00-\u9fa5]+|[a-z0-9]+/g) || [];
    var out = [];
    segs.forEach(function (seg) {
      if (/^[\u4e00-\u9fa5]+$/.test(seg)) {
        for (var i = 0; i < seg.length; i++) {
          out.push(seg[i]);
          if (i < seg.length - 1) out.push(seg.slice(i, i + 2));
        }
      } else out.push(seg);
    });
    return out;
  }
  function buildIndex(docs) {
    var N = docs.length;
    if (!N) return { docs: [], df: {}, tfs: [], lens: [], avg: 1, N: 0 };
    var df = {}, tfs = [], lens = [], total = 0;
    docs.forEach(function (d) {
      var tf = {}, toks = tokenize(d.text);
      toks.forEach(function (t) { tf[t] = (tf[t] || 0) + 1; });
      Object.keys(tf).forEach(function (t) { df[t] = (df[t] || 0) + 1; });
      tfs.push(tf); lens.push(toks.length); total += toks.length;
    });
    return { docs: docs, df: df, tfs: tfs, lens: lens, avg: total / N || 1, N: N };
  }
  function search(idx, query, topK) {
    var scores = new Array(idx.N).fill(0), seen = {};
    tokenize(query).forEach(function (t) {
      if (seen[t]) return; seen[t] = 1;
      var n = idx.df[t] || 0; if (!n) return;
      var idf = Math.log(1 + (idx.N - n + 0.5) / (n + 0.5));
      for (var i = 0; i < idx.N; i++) {
        var f = idx.tfs[i][t] || 0; if (!f) continue;
        scores[i] += idf * (f * 2.5) / (f + 1.5 * (0.25 + 0.75 * idx.lens[i] / idx.avg));
      }
    });
    return scores.map(function (s, i) { return { doc: idx.docs[i], score: s }; })
      .filter(function (x) { return x.score > 0; })
      .sort(function (a, b) { return b.score - a.score; }).slice(0, topK || 4);
  }
  function scopedDocs() {
    return state.docs.filter(function (d) {
      return (state.stage === 'all' || d.stage === state.stage) &&
             (state.subject === 'all' || d.subject === state.subject);
    });
  }
  function contextBlock(hits) {
    return hits.map(function (h, i) {
      var d = h.doc;
      var n = d.node;
      return '[' + (i + 1) + '] ' + d.title + '｜' + d.chapter + '｜来源:' + d.source +
        '\n' + (n ? '讲解: ' + n.summary +
          '\n核心关系: ' + (n.formula || '—') +
          '\n加深理解（本质直觉）: ' + ((n.deep_dive || [])[0] ? n.deep_dive[0].text : n.why || '—') +
          '\n加深理解（命题视角）: ' + ((n.deep_dive || [])[4] ? n.deep_dive[4].text : '—') +
          '\n常见错误: ' + (n.misconceptions || []).join('；') +
          '\n先修: ' + (n.prerequisites || []).join(', ') +
          '\n本章练习: ' + (n.questions || []).length + ' 道（' + (n.practice_plan || '分层练习') + '，需教师审核）'
          : d.text.slice(0, 600));
    }).join('\n\n');
  }

  /* ---------- 渲染 ---------- */
  function renderModes() {
    $('modeChips').innerHTML = MODES.map(function (m) {
      return '<button class="chip' + (m.id === state.mode ? ' active' : '') + '" data-mode="' + m.id + '">' +
        esc(m.name) + '</button>';
    }).join('');
    Array.prototype.forEach.call(document.querySelectorAll('.chip'), function (b) {
      b.onclick = function () {
        state.mode = b.dataset.mode; renderModes();
        setStatus('辅导方式：' + MODES.filter(function (m) { return m.id === state.mode; })[0].name);
      };
    });
  }
  function renderFilters() {
    var subs = {};
    state.docs.forEach(function (d) { if (d.subject) subs[d.subject] = 1; });
    var keys = Object.keys(subs).sort();
    $('subjectFilter').innerHTML = '<option value="all">全部学科</option>' +
      keys.map(function (k) { return '<option value="' + esc(k) + '">' + esc(k) + '</option>'; }).join('');
    $('subjectFilter').value = state.subject;
    $('scopeCount').textContent = '检索范围：' + scopedDocs().length + ' 个知识点 + ' + state.imported.length + ' 个自备片段';
  }
  function renderSources() {
    var ncCount = OPEN_SOURCES.filter(function (s) { return s.nc; }).length;
    var st = KG.stats || {};
    $('sourceList').innerHTML =
      '<li><b>教材章节</b><span>' + (st.textbooks || 0) + ' 种 · ' + (st.chapters || 0) + ' 章</span></li>' +
      '<li><b>分层练习</b><span>' + (st.chapter_practice_questions || 0) + ' 道 · 5:3:2</span></li>' +
      '<li><b>原创高区分度题</b><span>' + (st.original_questions || 0) + ' 道</span></li>' +
      '<li><b>精讲 / 节点</b><span>' + (st.featured_chapters || 0) + ' / ' + state.docs.length + '</span></li>' +
      '<li><b>自备资料</b><span>' + state.imported.length + ' 片段 · 仅本机</span></li>' +
      '<li><b>开放语料索引</b><span>' + OPEN_SOURCES.length + ' 项 · ' + ncCount + ' 项禁商用</span></li>';
    $('licenseList').innerHTML = OPEN_SOURCES.map(function (s) {
      return '<li><b>' + esc(s.name) + '</b><span class="tag ' + (s.nc ? 'nc' : 'ok') + '">' + (s.nc ? '禁商用' : '可商用*') + '</span></li>';
    }).join('');
  }
  function renderCitations() {
    if (!state.hits.length) { $('citations').innerHTML = '<p class="hint">提问后显示命中的知识点与章节。</p>'; return; }
    $('citations').innerHTML = state.hits.map(function (h, i) {
      var d = h.doc;
      return '<div class="cite"><b>[' + (i + 1) + '] ' + esc(d.title) + '</b> ' +
        '<span class="score">' + h.score.toFixed(2) + '</span>' +
        '<div class="meta">' + esc(d.chapter) + '</div>' +
        '<div class="meta">' + esc(d.source) + ' · ' + esc(d.license) + '</div></div>';
    }).join('');
  }
  function renderKG() {
    var list = scopedDocs().filter(function (d) { return d.node; });
    $('kgList').innerHTML = list.map(function (d) {
      var pre = (d.node.prerequisites || []).length ? '先修 ' + (d.node.prerequisites || []).length + ' 项' : '起点知识点';
      return '<div class="kgitem" data-id="' + esc(d.id) + '"><span class="kname">' + esc(d.title) + '</span>' +
        '<span class="kmeta">' + esc(d.subject) + ' · ' + (d.stage === 'highschool' ? '高中' : '大学') + ' · ' + pre + '</span></div>';
    }).join('') || '<p class="hint">当前筛选下没有知识点。</p>';
    Array.prototype.forEach.call(document.querySelectorAll('.kgitem'), function (el) {
      el.onclick = function () {
        var d = state.docs.filter(function (x) { return x.id === el.dataset.id; })[0];
        if (d) { var el2 = document.body.classList.contains('in-chat') ? $('input') : $('inputWelcome'); el2.value = '请讲解「' + d.title + '」，并结合它的先修知识点说明我该先补什么。'; el2.focus(); }
      };
    });
  }

  /* ---------- 教材章节浏览器 ---------- */
  function bookGroups() {
    var m = {};
    state.docs.forEach(function (d) {
      if (!d.node) return;
      var b = d.node.book || '其他';
      if (!m[b]) m[b] = { book: b, stage: d.stage, subject: d.subject, docs: [] };
      m[b].docs.push(d);
    });
    return Object.keys(m).sort(function (a, b) { return a.localeCompare(b, 'zh-CN'); })
      .map(function (k) { return m[k]; });
  }
  function renderBooks() {
    $('bookList').innerHTML = bookGroups().map(function (g) {
      var lab = g.stage === 'highschool' ? '高中' : g.stage === 'university' ? '大学' : '精讲';
      return '<div class="bookitem' + (state.activeBook === g.book ? ' active' : '') +
        '" data-book="' + esc(g.book) + '">' + esc(g.book) +
        '<span class="bm">' + lab + ' · ' + esc(g.subject) + ' · ' + g.docs.length + ' 章</span></div>';
    }).join('');
    Array.prototype.forEach.call($('bookList').children, function (el) {
      el.onclick = function () {
        state.activeBook = el.dataset.book; state.activeChapter = null;
        renderBooks(); renderChapters(); renderChapterDetail();
      };
    });
    var act = $('bookList').querySelector('.bookitem.active');
    if (act && act.scrollIntoView && !$('chapterModal').classList.contains('hidden')) {
      act.scrollIntoView({ block: 'nearest' });
    }
  }
  function renderChapters() {
    var g = bookGroups().filter(function (x) { return x.book === state.activeBook; })[0];
    if (!g) { $('chapterList').innerHTML = '<p class="hint">请选择左侧教材。</p>'; return; }
    $('chapterList').innerHTML = g.docs.map(function (d) {
      return '<div class="chapitem' + (state.activeChapter === d.id ? ' active' : '') +
        '" data-id="' + esc(d.id) + '">' + esc(d.node.unit) + ' ' + esc(d.title) +
        '<span class="cm">难度 ' + (d.node.difficulty || 2) + ' · ' +
        (d.node.questions || []).length + ' 道题' + (d.node.featured ? ' · 精讲' : '') + '</span></div>';
    }).join('');
    Array.prototype.forEach.call($('chapterList').children, function (el) {
      el.onclick = function () {
        state.activeChapter = el.dataset.id; renderChapters(); renderChapterDetail();
      };
    });
  }
  function addWrongFromQuestion(q, k) {
    var d = new Date(); d.setDate(d.getDate() + 1);
    state.wrong.unshift({ q: q.slice(0, 60), r: '待订正（来自章节练习）', k: k,
      next: d.toISOString().slice(0, 10) });
    writeLS(LS_WRONG, state.wrong); renderWrong(); setStatus('已加入错题本');
  }
  function renderQuestion(q, i) {
    var head = '<div class="qhead">' +
      '<span class="lv">' + esc(q.type_label || q.type || '练习') + ' · ' + esc(q.level || '分层') +
      ' · 难度 ' + (q.difficulty || 2) + ' · ' + (q.weight || 0) + ' 分</span>' +
      '<span>' + (q.bonus ? '附加题 · ' : '') + (q.auto_generated ? '自生成 · 建议教师审核' : '本项目原创 / 自撰') + '</span></div>';
    var body = '<div class="qtext">' + esc(q.q) + '</div>';
    if (q.options && q.options.length) {
      body += '<ul class="opts">' + q.options.map(function (o) { return '<li>' + esc(o) + '</li>'; }).join('') + '</ul>';
    }
    if (q.subquestions && q.subquestions.length) {
      body += '<ul class="subs">' + q.subquestions.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('') + '</ul>';
    }
    if (q.trend_tags && q.trend_tags.length) {
      body += '<div class="tags">趋势标签：' + esc(q.trend_tags.join(' / ')) + '</div>';
    }
    var answer = '<div class="answer hidden"><b>答案：</b>' + esc(q.a) +
      '\n<b>解析：</b>' + esc(q.analysis);
    if (q.rubric && q.rubric.length) {
      answer += '<div class="rubric"><b>评分要点</b><ul>' +
        q.rubric.map(function (r) { return '<li>' + esc(r) + '</li>'; }).join('') + '</ul></div>';
    }
    answer += '</div>';
    return '<div class="qcard" data-idx="' + i + '">' + head + body + answer +
      '<div class="qact"><button class="btn ghost" data-act="answer">查看答案与评分要点</button>' +
      '<button class="btn ghost" data-act="wrong">加入错题本</button></div></div>';
  }
  function renderChapterDetail() {
    var box = $('chapterDetail');
    if (!state.activeChapter) {
      box.innerHTML = '<p class="hint">选择中间一章，查看加深理解讲解与本章分层练习。</p>'; return;
    }
    var d = state.docs.filter(function (x) { return x.id === state.activeChapter; })[0];
    if (!d) return;
    var n = d.node;
    var html = '<div class="detail-title">' + esc(n.name) + '</div>' +
      '<div class="detail-meta">' + esc(n.book) + ' · ' + esc(n.unit) + ' · ' + esc(n.subject) +
      ' · 难度 ' + (n.difficulty || 2) + ' · ' + esc(d.license) + '</div>' +
      '<div class="plan-line">' + esc(n.practice_plan || KG.practice_plan || '') + '；全部自撰 / 自生成，不含任何真题或教辅原题</div>' +
      '<div class="dd-block"><b>核心关系</b><p>' + esc(n.formula || n.why || '—') + '</p></div>' +
      (n.deep_dive || []).map(function (s) {
        return '<div class="dd-block"><b>' + esc(s.title) + '</b><p>' + esc(s.text) + '</p></div>';
      }).join('') +
      '<div class="section-head">本章练习（' + (n.questions || []).length + ' 道）</div>';
    html += (n.questions || []).map(renderQuestion).join('');
    box.innerHTML = html;
    Array.prototype.forEach.call(box.querySelectorAll('[data-act]'), function (btn) {
      btn.onclick = function () {
        var card = btn.closest('.qcard');
        var q = (n.questions || [])[+card.dataset.idx];
        if (btn.dataset.act === 'answer') {
          var a = card.querySelector('.answer');
          a.classList.toggle('hidden');
          btn.textContent = a.classList.contains('hidden') ? '查看答案与评分要点' : '收起答案';
        } else if (q) addWrongFromQuestion(q.q, n.name);
      };
    });
  }
  function openBrowser() {
    $('chapterModal').classList.remove('hidden');
    var gs = bookGroups();
    if (!state.activeBook) {
      var prefer = gs.filter(function (g) { return /人教A版 必修第一册/.test(g.book); })[0];
      state.activeBook = prefer ? prefer.book : (gs.length ? gs[0].book : null);
    }
    if (!state.activeChapter) {
      var g = gs.filter(function (x) { return x.book === state.activeBook; })[0];
      state.activeChapter = g && g.docs.length ? g.docs[0].id : null;
    }
    renderBooks(); renderChapters(); renderChapterDetail();
  }
  function closeBrowser() { $('chapterModal').classList.add('hidden'); }

  /* ---------- 命题趋势与版权说明 ---------- */
  function li(list) {
    return '<ul>' + (list || []).map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>';
  }
  function table(headers, rows) {
    return '<table><thead><tr>' + headers.map(function (h) { return '<th>' + esc(h) + '</th>'; }).join('') +
      '</tr></thead><tbody>' + rows.map(function (r) {
        return '<tr>' + r.map(function (c) { return '<td>' + esc(c) + '</td>'; }).join('') + '</tr>';
      }).join('') + '</tbody></table>';
  }
  function renderTrends() {
    var box = $('trendBody');
    if (!TRENDS.version) { box.innerHTML = '<p class="hint">趋势数据未加载（trends.js）。</p>'; return; }
    var tr = TRENDS.trend_research || {}, cp = TRENDS.compliance || {}, ds = TRENDS.distribution || {};
    var h = '';
    h += '<h4>调研结论</h4>';
    h += '<p class="lead">' + esc(tr.verdict || '') + '</p>';
    h += '<p class="hint">原始判断：' + esc(tr.user_claim || '') + '。调研后区分事实与解读如下。</p>';
    h += '<h4>已核实事实</h4>' + li(tr.verified_facts);
    h += '<h4>教学解读</h4>' + li(tr.interpretation);
    h += '<h4>未证实 / 不成立</h4>' + li(tr.not_verified);

    h += '<h4>五个难度旋钮</h4>';
    h += table(['旋钮', '含义'], (TRENDS.difficulty_knobs || []).map(function (k) { return [k.name, k.desc]; }));
    h += '<h4>七类题型</h4>';
    h += table(['题型', '考查意图', '评分要点'], (TRENDS.item_types || []).map(function (t) {
      return [t.name, t.intent, t.scoring];
    }));
    h += '<h4>难度配比与区分度</h4>';
    var cpRatio = ds.chapter_practice || {}, full = ds.full_mock_exam || {}, di = ds.discrimination_index || {};
    h += '<p>章节练习按分值 <b>' + (cpRatio.basic || 5) + ' : ' + (cpRatio.medium || 3) + ' : ' + (cpRatio.high || 2) +
      '</b>（基础 / 中档 / 高区分度），' + esc(cpRatio.implementation || '') + '。整卷模拟另建议 ' +
      (full.basic || 3) + ' : ' + (full.medium || 5) + ' : ' + (full.high || 2) + '。</p>';
    h += '<p>区分度按 <b>' + esc(di.formula || 'D = P_H − P_L') + '</b> 估计；' + esc(di.note || '') + '</p>';
    h += '<h4>命题规则</h4>' + li(TRENDS.design_rules);

    h += '<h4>试卷来源核查结论</h4>';
    h += '<p class="lead">' + esc(cp.finding || '') + '</p>';
    h += '<p>目标页：' + esc((cp.target_page || {}).title || '') + '（' + esc((cp.target_page || {}).url || '') + '）。' +
      esc((cp.target_page || {}).observed_content || '') + '</p>';
    h += table(['依据', '位置', '要点'], (cp.evidence || []).map(function (e) {
      return [e.item, e.url || '页面声明', e.note];
    }));
    h += '<h4>禁止事项</h4>' + li(cp.forbidden_actions);
    h += '<h4>合法替代路径</h4>' + li(cp.lawful_alternatives);
    h += '<h4>开源真题仓库许可核查</h4>';
    h += table(['仓库', '许可', '判断'], (cp.open_repo_license_audit || []).map(function (r) {
      return [r.name, r.license, r.verdict];
    }));
    h += '<p><b>' + esc(cp.strict_verdict || '') + '</b></p>';
    h += '<h4>本项目采取的做法</h4>' + li(cp.project_policy);
    h += '<p class="note">' + esc(TRENDS.disclaimer || '') + '</p>';
    box.innerHTML = h;
  }
  function openTrends() { renderTrends(); $('trendModal').classList.remove('hidden'); }
  function closeTrends() { $('trendModal').classList.add('hidden'); }

  function renderWrong() {
    $('wrongList').innerHTML = state.wrong.length ? state.wrong.map(function (w, i) {
      return '<li><span class="del" data-i="' + i + '">×</span><b>' + esc(w.q) + '</b><br>' +
        esc(w.r) + ' · ' + esc(w.k || '') + ' · 复习 ' + esc(w.next) + '</li>';
    }).join('') : '<li>暂无记录</li>';
    Array.prototype.forEach.call(document.querySelectorAll('.wronglist .del'), function (el) {
      el.onclick = function () { state.wrong.splice(+el.dataset.i, 1); writeLS(LS_WRONG, state.wrong); renderWrong(); };
    });
  }
  function addMsg(role, html) {
    var box = $('chat');
    var div = document.createElement('div');
    div.className = 'msg ' + role;
    if (role === 'sys') {
      div.innerHTML = '<div class="body">' + html + '</div>';
    } else {
      var who = role === 'user' ? '你' : '学序';
      var av = role === 'ai' ? '<div class="av">学</div>' : '';
      div.innerHTML = av + '<div><div class="who">' + who + '</div><div class="body">' + html + '</div></div>';
    }
    box.appendChild(div); box.scrollTop = box.scrollHeight;
  }

  /* ---------- 回答：真实模型（经同源代理） or 坦诚的检索演示 ---------- */
  function demoAnswer(q, hits) {
    var head = '【检索演示模式｜未调用任何大模型】\n下面只列出命中的知识库片段，不是模型生成的回答。配置模型后才会得到教学解答。\n';
    if (!hits.length) return head + '\n当前筛选范围内没有命中知识点。试试放宽学科筛选，或导入自备资料。';
    var body = hits.map(function (h, i) {
      var d = h.doc, n = d.node;
      var parts = ['[' + (i + 1) + '] ' + d.title + ' · ' + d.chapter];
      if (n) {
        parts.push('讲解：' + n.summary);
        if (n.formula) parts.push('核心关系：' + n.formula);
        if (n.deep_dive && n.deep_dive[0]) parts.push('加深理解 · ' + n.deep_dive[0].title + '：' + n.deep_dive[0].text);
        if (n.deep_dive && n.deep_dive[4]) parts.push('命题视角：' + n.deep_dive[4].text);
        parts.push('常见错误：' + (n.misconceptions || []).join('；'));
        parts.push('先修：' + ((n.prerequisites || []).join('、') || '无'));
        parts.push('本章练习：' + (n.questions || []).length + ' 道（点侧栏「教材章节练习」逐章练习）');
      } else parts.push(d.text.slice(0, 400));
      return parts.join('\n');
    }).join('\n\n');
    return head + '\n' + body + '\n\n下一步：在左侧「模型设置」填入接口地址与 Key，即可用六种辅导方式生成教学回应。';
  }
  async function callModel(q, hits) {
    var mode = MODES.filter(function (m) { return m.id === state.mode; })[0];
    var sys = mode.prompt + '\n\n【知识库片段】\n' + (contextBlock(hits) || '（无命中片段，请说明依据不足）') +
      '\n\n要求：中文作答；引用格式为 [编号]；不得声称引用了未提供的教材页码或原文；不得复制任何第三方真题。';
    var msgs = [{ role: 'system', content: sys }]
      .concat(state.history.slice(-6))
      .concat([{ role: 'user', content: q }]);
    // 经本站同源代理转发，规避浏览器跨域（CORS）
    var resp = await fetch('/api/chat', {
      method: 'POST', cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base: state.api.base, key: state.api.key, model: state.api.model,
        messages: msgs, temperature: 0.4 })
    });
    if (!resp.ok) {
      var msg = '';
      try { var j = await resp.json(); msg = (j && j.error) || ('HTTP ' + resp.status); }
      catch (e) { msg = 'HTTP ' + resp.status; }
      throw new Error(msg);
    }
    var data = await resp.json();
    return (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || '（模型返回为空）';
  }

  function activeInput() { return document.body.classList.contains('in-chat') ? $('input') : $('inputWelcome'); }
  function enterChat() { document.body.classList.add('in-chat'); }
  function showWelcome() { document.body.classList.remove('in-chat'); }

  async function send() {
    if (state.busy) return;
    var el = activeInput();
    var q = el.value.trim(); if (!q) return;
    el.value = '';
    enterChat();
    state.busy = true; $('sendBtn').disabled = true; $('sendWelcome').disabled = true;
    addMsg('user', esc(q));
    setStatus('检索中…');
    var idx = buildIndex(scopedDocs().concat(state.imported));
    var hits = search(idx, q, 4);
    state.hits = hits; renderCitations();
    if (state.api) {
      setStatus('调用模型中…');
      addMsg('sys', '检索到 ' + hits.length + ' 条依据，已连同教学指令经本站代理送入模型。');
      try {
        var ans = await callModel(q, hits);
        addMsg('ai', esc(ans));
        state.history.push({ role: 'user', content: q }, { role: 'assistant', content: ans });
        setStatus('完成');
      } catch (e) {
        addMsg('sys', '模型调用失败：' + esc(e.message) + '。已降级为检索演示，不伪造回答。');
        addMsg('ai', esc(demoAnswer(q, hits)));
        setStatus('模型失败，已降级');
      }
    } else {
      addMsg('ai', esc(demoAnswer(q, hits)));
      setStatus('检索演示完成（未配置模型）');
    }
    state.busy = false; $('sendBtn').disabled = false; $('sendWelcome').disabled = false;
  }

  /* ---------- 自备资料导入（全程本地） ---------- */
  function splitText(text, name, license) {
    var blocks = text.split(/\n\s*\n+/).map(function (s) { return s.trim(); }).filter(function (s) { return s.length > 20; });
    var out = [];
    blocks.forEach(function (b) {
      for (var i = 0; i < b.length; i += 500) {
        out.push({ id: 'local-' + out.length, title: name + ' 片段 ' + (out.length + 1),
          chapter: '用户自备资料（本地）', stage: state.stage === 'university' ? 'university' : 'highschool',
          subject: state.subject === 'all' ? '自备' : state.subject, source: name + '（本机）',
          license: license || 'user_local', text: b.slice(i, i + 500) });
      }
    });
    return out;
  }
  function handleFiles(files) {
    var pending = files.length;
    if (!pending) return;
    Array.prototype.forEach.call(files, function (f) {
      var r = new FileReader();
      r.onload = function () {
        var txt = String(r.result || '');
        if (/\.json$/i.test(f.name)) {
          try {
            var j = JSON.parse(txt);
            if (Array.isArray(j)) {
              txt = j.map(function (o) {
                return typeof o === 'string' ? o : (o.text || o.content || o.summary || o.question || JSON.stringify(o));
              }).join('\n\n');
            }
          } catch (e) { /* 按纯文本处理 */ }
        }
        var added = splitText(txt, f.name, 'user_local');
        state.imported = state.imported.concat(added);
        pending--;
        if (!pending) {
          renderSources(); renderFilters();
          setStatus('已导入 ' + added.length + ' 个片段（仅本机，未上传）');
          addMsg('sys', '已把 ' + esc(f.name) + ' 等文件切分为 ' + state.imported.length + ' 个本地片段并加入检索池。这些片段不会上传，也不会写入任何分发文件。');
        }
      };
      r.readAsText(f, 'utf-8');
    });
  }

  function openDrawer() { $('citeDrawer').classList.add('open'); $('drawerMask').classList.add('open'); }
  function closeDrawer() { $('citeDrawer').classList.remove('open'); $('drawerMask').classList.remove('open'); }

  /* ---------- 初始化 ---------- */
  function init() {
    state.docs = KG.nodes.map(nodeToDoc);
    state.api = readLS(LS_API, null) || readLS('xuexu.api.0.2.0', null) || readLS('xuexu.api.0.1.0', null);
    state.wrong = readLS(LS_WRONG, []);
    if (!state.wrong || !state.wrong.length) state.wrong = readLS('xuexu.wrongbook.0.2.0', []) || [];
    renderModes(); renderFilters(); renderSources(); renderCitations(); renderKG(); renderWrong();

    $('apiBase').value = state.api ? state.api.base : '';
    $('apiKey').value = state.api ? state.api.key : '';
    $('apiModel').value = state.api ? state.api.model : '';
    updateBadge();
    var st0 = KG.stats || {};
    addMsg('sys', '学序 v' + VERSION + '：' + (st0.textbooks || 0) + ' 种教材 / ' +
      (st0.chapters || 0) + ' 章 / ' + (st0.questions || 0) + ' 道题，覆盖高中数理化与大学理工核心课程。' +
      '<h4>逐章练习</h4>点侧栏「教材章节练习」→ 选教材 → 选章：每章 5 段加深理解、5 道分层练习（基础 2 / 中档 2 / 高区分度 1，分值 5:3:2），含答案、解析与评分要点。' +
      '<h4>命题趋势</h4>侧栏「命题趋势与版权」记录近五年趋势调研、七类题型与试卷来源核查结论。' +
      '<h4>内容边界</h4>只含书目 / 章节骨架与本项目自撰讲解、题目，不含教材、教辅、真题或模考卷原文；' +
      (st0.original_questions || 0) + ' 道原创高区分度题为手工校订，其余标注「自生成 · 建议教师审核」。' +
      '<h4>演示模式</h4>未配置模型时只返回检索片段并明确标注，不会假装是模型回答。');

    $('quickRow').innerHTML = [
      '导数为零一定是极值点吗？', '新定义题该从哪里下手',
      '多选题怎样逐项判断', '帮我讲讲化学平衡的移动'
    ].map(function (t) { return '<button>' + esc(t) + '</button>'; }).join('');
    Array.prototype.forEach.call($('quickRow').children, function (b) {
      b.onclick = function () { var el = activeInput(); el.value = b.textContent; el.focus(); };
    });

    $('stageFilter').onchange = function () { state.stage = this.value; renderFilters(); renderKG(); state.hits = []; renderCitations(); };
    $('subjectFilter').onchange = function () { state.subject = this.value; renderFilters(); renderKG(); state.hits = []; renderCitations(); };
    $('sendBtn').onclick = send;
    $('sendWelcome').onclick = send;
    $('input').onkeydown = function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
    $('inputWelcome').onkeydown = function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
    $('fileInput').onchange = function () { handleFiles(this.files); this.value = ''; };
    $('saveApi').onclick = function () {
      var b = $('apiBase').value.trim(), k = $('apiKey').value.trim(), m = $('apiModel').value.trim();
      if (!b || !k || !m) { setStatus('请填完整接口地址 / key / 模型名'); return; }
      state.api = { base: b, key: k, model: m }; writeLS(LS_API, state.api); updateBadge();
      setStatus('模型已配置（密钥仅存本机，经本站代理转发）');
    };
    $('clearApi').onclick = function () {
      state.api = null; writeLS(LS_API, null);
      $('apiBase').value = $('apiKey').value = $('apiModel').value = '';
      updateBadge(); setStatus('已切回检索演示模式');
    };
    $('apiPreset').onchange = function () {
      var p = PRESETS[this.value];
      if (p) { $('apiBase').value = p.base; $('apiModel').value = p.model; }
    };
    $('addWrong').onclick = function () {
      var q = $('wrongQ').value.trim(), r = $('wrongR').value.trim(); if (!q) return;
      var k = state.hits.length ? state.hits[0].doc.title : '未关联';
      var d = new Date(); d.setDate(d.getDate() + 1);
      state.wrong.unshift({ q: q, r: r || '未填错因', k: k, next: d.toISOString().slice(0, 10) });
      writeLS(LS_WRONG, state.wrong); $('wrongQ').value = $('wrongR').value = ''; renderWrong();
    };

    $('newChat').onclick = function () {
      state.history = []; state.hits = []; $('chat').innerHTML = ''; showWelcome(); setStatus('就绪');
    };
    $('navBrowser').onclick = openBrowser;
    $('navTrends').onclick = openTrends;
    $('navCites').onclick = openDrawer;
    $('closeDrawer').onclick = closeDrawer;
    $('drawerMask').onclick = closeDrawer;
    $('collapseSide').onclick = function () { $('app').classList.add('side-collapsed'); };
    $('showSide').onclick = function () { $('app').classList.remove('side-collapsed'); };
    if (window.innerWidth <= 860) $('app').classList.add('side-collapsed');

    $('closeBrowser').onclick = closeBrowser;
    $('chapterModal').onclick = function (e) { if (e.target === $('chapterModal')) closeBrowser(); };
    $('closeTrends').onclick = closeTrends;
    $('trendModal').onclick = function (e) { if (e.target === $('trendModal')) closeTrends(); };
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { closeBrowser(); closeTrends(); closeDrawer(); }
    });
    var st = KG.stats || {};
    var statTxt = (st.textbooks || 0) + ' 种教材 / ' + (st.chapters || 0) + ' 章 / ' + (st.questions || 0) + ' 道题';
    $('coverageLine').textContent = '高中数理化 · 大学理工 ｜ 教材章节练习 ｜ ' + statTxt;
    $('modalStat').textContent = statTxt + ' · 每章 5 段讲解 + 5 道分层练习';
    renderBooks(); renderChapters(); renderChapterDetail();

    try {
      var view = new URLSearchParams(window.location.search).get('view');
      if (view === 'browser') openBrowser();
      if (view === 'trends') openTrends();
    } catch (e) { /* 老浏览器忽略 */ }
  }
  function updateBadge() {
    var b = $('modeBadge');
    b.textContent = state.api ? '模型已接入 · ' + state.api.model : '检索演示模式';
    $('apiStatus').textContent = state.api ? ('已接入：' + state.api.model) : '未配置：返回检索演示模式';
  }

  init();
})();
