/* 学序 v0.1.0 — 零依赖教材锚定辅导工作台
   设计参考：OmniEdu（能力/教学指令分类、课程锚定、错因诊断）
             DeepTutor（可溯源 RAG、版本化来源、错题与掌握度）
   合规：不内置任何教材/教辅原文；全文仅来自用户本地导入，不上传、不分发。 */
(function () {
  'use strict';

  var KG = window.KG || { nodes: [] };
  var VERSION = '0.1.0';
  var LS_API = 'xuexu.api.' + VERSION;
  var LS_WRONG = 'xuexu.wrongbook.' + VERSION;

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
      prompt: '你是命题老师。依据【知识库片段】生成 2 道由易到难的题目，附标准答案与逐条解析，并标注每题考查的知识点与教材章节。用 [编号] 标注依据。题目须自撰，不得复制任何教辅原题。' }
  ];

  /* B 级开放语料：许可标签决定能否进入产品化训练/服务 */
  var OPEN_SOURCES = [
    { name: 'opendatalab/K12textbook', license: 'Apache-2.0（原教材版权另计）', nc: true, url: 'https://huggingface.co/datasets/opendatalab/K12textbook' },
    { name: 'GAOKAO-Bench', license: '试题版权另计，研究用途', nc: true, url: 'https://github.com/OpenLMLab/GAOKAO-Bench' },
    { name: 'CJEval', license: '仅学术研究，禁商用', nc: true, url: 'https://github.com/smilewhc/cjeval' },
    { name: 'C-Eval / CMMLU', license: 'CC BY-NC-SA 4.0，禁商用', nc: true, url: 'https://github.com/haonan-li/CMMLU' },
    { name: 'CMATH', license: 'CC BY 4.0，可商用需署名', nc: false, url: 'https://github.com/XiaoMi/cmath' },
    { name: 'OmniEdu 训练数据集', license: '按数据集卡与上游来源核对', nc: true, url: 'https://huggingface.co/datasets/lhpku20010120/Omni-Edu' }
  ];

  var state = {
    mode: 'solve', stage: 'all', subject: 'all',
    api: null, docs: [], imported: [], hits: [],
    history: [], wrong: [], busy: false
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
    return {
      id: n.id, title: n.name, chapter: n.chapter || '—',
      stage: n.stage, subject: n.subject, node: n,
      source: '内置知识点骨架（本项目自撰）', license: 'self-authored',
      text: [n.name, n.chapter, n.summary, n.formula, (n.misconceptions || []).join(' '),
             n.example ? n.example.q + ' ' + n.example.a : '',
             (n.prerequisites || []).join(' ')].join('\n')
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
      return '[' + (i + 1) + '] ' + d.title + '｜' + d.chapter + '｜来源:' + d.source +
        '\n' + (d.node ? '讲解: ' + d.node.summary + '\n常见错误: ' + (d.node.misconceptions || []).join('；') +
          '\n先修: ' + (d.node.prerequisites || []).join(', ') : d.text.slice(0, 600));
    }).join('\n\n');
  }

  /* ---------- 渲染 ---------- */
  function renderModes() {
    $('modeList').innerHTML = MODES.map(function (m) {
      return '<button class="mode-btn' + (m.id === state.mode ? ' active' : '') + '" data-mode="' + m.id + '">' +
        '<b>' + esc(m.name) + '</b><span>' + esc(m.desc) + '</span></button>';
    }).join('');
    Array.prototype.forEach.call(document.querySelectorAll('.mode-btn'), function (b) {
      b.onclick = function () { state.mode = b.dataset.mode; renderModes(); setStatus('已切换：' + MODES.filter(function (m) { return m.id === state.mode; })[0].name); };
    });
  }
  function renderFilters() {
    var subs = {};
    state.docs.forEach(function (d) { if (d.subject) subs[d.subject] = 1; });
    var keys = Object.keys(subs).sort();
    $('subjectFilter').innerHTML = '<option value="all">全部学科</option>' +
      keys.map(function (k) { return '<option value="' + esc(k) + '">' + esc(k) + '</option>'; }).join('');
    $('subjectFilter').value = state.subject;
    $('scopeCount').textContent = '当前检索池：' + scopedDocs().length + ' 个知识点文档 + ' + state.imported.length + ' 个自备片段';
  }
  function renderSources() {
    var ncCount = OPEN_SOURCES.filter(function (s) { return s.nc; }).length;
    $('sourceList').innerHTML =
      '<li><b>内置知识点骨架</b><span>' + state.docs.length + ' 节点 · 自撰</span></li>' +
      '<li><b>用户自备资料</b><span>' + state.imported.length + ' 片段 · 仅本机</span></li>' +
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
        if (d) { $('input').value = '请讲解「' + d.title + '」，并结合它的先修知识点说明我该先补什么。'; $('input').focus(); }
      };
    });
  }
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
    var av = role === 'user' ? '我' : role === 'sys' ? '!' : '师';
    div.innerHTML = '<div class="av">' + av + '</div><div class="body">' + html + '</div>';
    box.appendChild(div); box.scrollTop = box.scrollHeight;
  }

  /* ---------- 回答：真实模型 or 坦诚的检索演示 ---------- */
  function demoAnswer(q, hits) {
    var head = '【检索演示模式｜未调用任何大模型】\n本轮只做知识库检索，下面的内容是命中的知识点片段，不是模型生成的回答。配置模型后才会得到教学解答。\n';
    if (!hits.length) return head + '\n当前筛选范围内没有命中知识点。试试放宽学科筛选，或导入自备资料。';
    var body = hits.map(function (h, i) {
      var d = h.doc, n = d.node;
      var parts = ['[' + (i + 1) + '] ' + d.title + ' · ' + d.chapter];
      if (n) {
        parts.push('讲解：' + n.summary);
        if (n.formula) parts.push('核心式：' + n.formula);
        parts.push('常见错误：' + (n.misconceptions || []).join('；'));
        parts.push('先修：' + ((n.prerequisites || []).join('、') || '无'));
      } else parts.push(d.text.slice(0, 400));
      return parts.join('\n');
    }).join('\n\n');
    return head + '\n' + body + '\n\n下一步：配置模型后可用「分步提示 / 错因诊断 / 苏格拉底追问」等模式生成教学回应。';
  }
  async function callModel(q, hits) {
    var mode = MODES.filter(function (m) { return m.id === state.mode; })[0];
    var sys = mode.prompt + '\n\n【知识库片段】\n' + (contextBlock(hits) || '（无命中片段，请说明依据不足）') +
      '\n\n要求：中文作答；引用格式为 [编号]；不得声称引用了未提供的教材页码或原文。';
    var msgs = [{ role: 'system', content: sys }]
      .concat(state.history.slice(-6))
      .concat([{ role: 'user', content: q }]);
    var base = state.api.base.replace(/\/+$/, '');
    var url = /\/chat\/completions$/.test(base) ? base : base + '/chat/completions';
    var resp = await fetch(url, {
      method: 'POST', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + state.api.key },
      body: JSON.stringify({ model: state.api.model, messages: msgs, temperature: 0.4, stream: false })
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status + ' ' + (await resp.text()).slice(0, 200));
    var data = await resp.json();
    return (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || '（模型返回为空）';
  }

  async function send() {
    if (state.busy) return;
    var q = $('input').value.trim(); if (!q) return;
    $('input').value = '';
    state.busy = true; $('sendBtn').disabled = true;
    addMsg('user', esc(q));
    setStatus('检索中…');
    var idx = buildIndex(scopedDocs().concat(state.imported));
    var hits = search(idx, q, 4);
    state.hits = hits; renderCitations();
    if (state.api) {
      setStatus('调用模型中…');
      addMsg('sys', '检索到 ' + hits.length + ' 条依据，已连同教学指令送入模型。');
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
    state.busy = false; $('sendBtn').disabled = false;
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

  /* ---------- 初始化 ---------- */
  function init() {
    state.docs = KG.nodes.map(nodeToDoc);
    state.api = readLS(LS_API, null);
    state.wrong = readLS(LS_WRONG, []);
    renderModes(); renderFilters(); renderSources(); renderCitations(); renderKG(); renderWrong();

    $('apiBase').value = state.api ? state.api.base : '';
    $('apiKey').value = state.api ? state.api.key : '';
    $('apiModel').value = state.api ? state.api.model : '';
    updateBadge();
    addMsg('sys', '学序 v' + VERSION + ' 已就绪。内置 ' + state.docs.length +
      ' 个自撰知识点（高中数理化 + 大学理工），全部标注教材章节映射，不含任何教材原文。' +
      '<h4>合规边界</h4>教材与练习册全文不内置、不抓取、不分发；如需全文检索，请导入你自己持有的 TXT/MD 文件。' +
      '<h4>演示模式</h4>未配置模型时，本工作台只返回检索到的知识点片段并明确标注，不会假装是 AI 生成的回答。');

    $('quickRow').innerHTML = [
      '导数为零一定是极值点吗？', '我算电磁感应时总把磁通量和变化率搞混',
      '矩阵的秩和方程组解空间有什么关系', '帮我讲讲化学平衡的移动'
    ].map(function (t) { return '<button>' + esc(t) + '</button>'; }).join('');
    Array.prototype.forEach.call($('quickRow').children, function (b) {
      b.onclick = function () { $('input').value = b.textContent; $('input').focus(); };
    });

    $('stageFilter').onchange = function () { state.stage = this.value; renderFilters(); renderKG(); state.hits = []; renderCitations(); };
    $('subjectFilter').onchange = function () { state.subject = this.value; renderFilters(); renderKG(); state.hits = []; renderCitations(); };
    $('sendBtn').onclick = send;
    $('input').onkeydown = function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
    $('fileInput').onchange = function () { handleFiles(this.files); this.value = ''; };
    $('saveApi').onclick = function () {
      var b = $('apiBase').value.trim(), k = $('apiKey').value.trim(), m = $('apiModel').value.trim();
      if (!b || !k || !m) { setStatus('请填完整 endpoint / key / model'); return; }
      state.api = { base: b, key: k, model: m }; writeLS(LS_API, state.api); updateBadge();
      setStatus('模型已配置（密钥仅存本机 localStorage）');
    };
    $('clearApi').onclick = function () {
      state.api = null; writeLS(LS_API, null);
      $('apiBase').value = $('apiKey').value = $('apiModel').value = '';
      updateBadge(); setStatus('已切回检索演示模式');
    };
    $('addWrong').onclick = function () {
      var q = $('wrongQ').value.trim(), r = $('wrongR').value.trim(); if (!q) return;
      var k = state.hits.length ? state.hits[0].doc.title : '未关联';
      var d = new Date(); d.setDate(d.getDate() + 1);
      state.wrong.unshift({ q: q, r: r || '未填错因', k: k, next: d.toISOString().slice(0, 10) });
      writeLS(LS_WRONG, state.wrong); $('wrongQ').value = $('wrongR').value = ''; renderWrong();
    };
  }
  function updateBadge() {
    var b = $('modeBadge');
    b.textContent = state.api ? '模型已接入 · ' + state.api.model : '检索演示模式';
    b.className = 'badge' + (state.api ? ' ok' : '');
  }

  init();
})();
