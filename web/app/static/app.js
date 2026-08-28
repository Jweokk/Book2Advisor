/* Book2Advisor — 前端交互
 * 零外部依赖：原生 fetch + DOM。零 SVG 图标、零 emoji 装饰。
 * 提交问题 → POST /api/ask → 渐进渲染 8 段 Method Trace。 */

"use strict";

/* ---------- DOM 工具（一律用 textContent，杜绝 XSS） ---------- */
function el(tag, className, text) {
  var node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function sectionTitle(text) {
  return el("h2", "section-title", text);
}


/* ---------- 轻量 markdown 渲染（DOM 构建，textContent，防 XSS） ---------- */
/* 支持：**加粗**、- 无序列表、1. 有序列表、空行分段。其余原样文本。 */
function renderInline(str) {
  var span = document.createElement("span");
  var parts = String(str).split(/\*\*([^*]+)\*\*/g);
  for (var i = 0; i < parts.length; i++) {
    if (parts[i] === "") continue;
    if (i % 2 === 1) {
      var b = document.createElement("strong");
      b.textContent = parts[i];
      span.appendChild(b);
    } else {
      span.appendChild(document.createTextNode(parts[i]));
    }
  }
  return span;
}

function renderMdBlock(text) {
  var frag = document.createDocumentFragment();
  var lines = String(text || "").split("\n");
  var para = null, list = null;
  function flushPara() { if (para) { frag.appendChild(para); para = null; } }
  function flushList() { if (list) { frag.appendChild(list); list = null; } }
  lines.forEach(function (line) {
    var t = line.trim();
    if (!t) { flushPara(); flushList(); return; }
    var ulMatch = /^[-*\u2022]\s+(.*)$/.exec(t);
    var olMatch = /^\d+[.\u3001]\s+(.*)$/.exec(t);
    if (ulMatch || olMatch) {
      flushPara();
      if (!list) { list = document.createElement("ul"); list.className = "md-list"; }
      var li = document.createElement("li");
      li.appendChild(renderInline(ulMatch ? ulMatch[1] : olMatch[1]));
      list.appendChild(li);
    } else {
      flushList();
      if (!para) { para = document.createElement("p"); para.className = "prose"; }
      if (para.childNodes.length) para.appendChild(document.createTextNode(" "));
      para.appendChild(renderInline(t));
    }
  });
  flushPara(); flushList();
  return frag;
}

/* ---------- 8 段渲染 ---------- */

/* 段1 问题理解（小字灰） */
function renderQuestion(result) {
  var sec = el("section", "section");
  sec.appendChild(sectionTitle("问题理解"));
  sec.appendChild(el("p", "question-echo", "问题：" + result.question));
  var cls = result.classification || {};
  var text = "问题分类：" + (cls.name || cls.diagnostic_id || "—");
  if (cls.reason) text += "（" + cls.reason + "）";
  if (cls.fallback) {
    text += "；说明：问题与现有诊断路径均不完全匹配，已按顺序采用第一条诊断路径。";
  }
  sec.appendChild(el("p", "question-classify", text));
  return sec;
}

/* 段2 诊断路径：每行一张步骤卡片 */
function renderDiagnosis(result) {
  var sec = el("section", "section");
  sec.appendChild(sectionTitle("诊断路径"));
  sec.appendChild(el("p", "section-desc", "按人物方法，先看什么："));
  var lines = String(result.diagnosis || "")
    .split("\n").map(function (s) { return s.trim(); }).filter(Boolean);
  if (!lines.length) lines.push("（无诊断内容）");
  lines.forEach(function (line) {
    var card = el("div", "step-card");
    card.appendChild(renderInline(line));
    sec.appendChild(card);
  });
  return sec;
}

/* 段3 采用的方法：原则/规则条目，原生 details 展开证据，level 徽标 */
var LEVEL_CN = {"E5": "极高", "E4": "高", "E3": "中", "E2": "低", "E1": "假设"};

function evidenceList(evidence) {
  var list = el("ul", "evidence-list");
  (evidence || []).forEach(function (ev) {
    var li = el("li");
    li.appendChild(el("span", "evidence-quote", "「" + (ev.quote || "") + "」"));
    if (ev.loc) li.appendChild(el("span", "evidence-meta", "[" + ev.loc + "]"));
    if (ev.level) li.appendChild(el("span", "badge", LEVEL_CN[ev.level] || ev.level));
    list.appendChild(li);
  });
  return list;
}

function methodCard(kind, item) {
  var card = el("details", "method-card");
  var summary = el("summary");
  summary.appendChild(el("span", "method-kind", kind));
  summary.appendChild(el("span", "method-id", item.name || item.id));
  summary.appendChild(el("span", "method-statement", item.statement));
  card.appendChild(summary);
  var body = el("div", "method-body");
  if (item.confidence) {
    body.appendChild(el("p", "badge-row", "置信度：" + item.confidence));
  }
  if ((item.evidence || []).length) body.appendChild(evidenceList(item.evidence));
  card.appendChild(body);
  return card;
}

function ruleCard(rule) {
  var card = el("details", "method-card");
  var summary = el("summary");
  summary.appendChild(el("span", "method-kind", "规则"));
  summary.appendChild(el("span", "method-id", rule.name || rule.id));
  var triggers = (rule.trigger || []).join("；");
  summary.appendChild(el("span", "method-statement", "触发条件：「" + triggers + "」"));
  card.appendChild(summary);
  var body = el("div", "method-body");
  var decisions = rule.decisions || {};
  var dText = Object.keys(decisions)
    .map(function (k) { return k + "→" + decisions[k]; }).join("；");
  if (dText) body.appendChild(el("p", "badge-row", "决策：" + dText));
  if (rule.exceptions) body.appendChild(el("p", "badge-row", "例外：" + rule.exceptions));
  if ((rule.evidence || []).length) body.appendChild(evidenceList(rule.evidence));
  card.appendChild(body);
  return card;
}

function renderMethods(result) {
  var sec = el("section", "section");
  sec.appendChild(sectionTitle("采用的方法"));
  var wrap = el("div", "method-list");
  (result.principles || []).forEach(function (p) {
    wrap.appendChild(methodCard("原则", p));
  });
  (result.rules || []).forEach(function (r) {
    wrap.appendChild(ruleCard(r));
  });
  if (!(result.principles || []).length && !(result.rules || []).length) {
    wrap.appendChild(el("p", "empty", "（未命中任何方法）"));
  }
  sec.appendChild(wrap);
  return sec;
}

/* 段4 相关案例：卡片（问题/决策/行动/结果） */
function renderCases(result) {
  var sec = el("section", "section");
  sec.appendChild(sectionTitle("相关案例"));
  var cases = result.cases || [];
  if (!cases.length) {
    sec.appendChild(el("p", "empty", "（未检索到高度相关案例）"));
    return sec;
  }
  cases.forEach(function (c) {
    var card = el("div", "case-card");
    card.appendChild(el("div", "case-title", c.name || c.id));
    card.appendChild(el("p", "case-line", "问题：" + (c.problem || "")));
    card.appendChild(el("p", "case-line", "决策：" + (c.decision || "")));
    if (c.action) card.appendChild(el("p", "case-line", "行动：" + c.action));
    card.appendChild(el("p", "case-line", "结果：" + (c.outcome || "")));
    sec.appendChild(card);
  });
  return sec;
}

/* 段5/6 建议、例外与风险：正文段落 */
function renderProse(title, text) {
  var sec = el("section", "section");
  sec.appendChild(sectionTitle(title));
  var textStr = String(text || "").trim();
  if (!textStr) { sec.appendChild(el("p", "prose", "（无内容）")); return sec; }
  sec.appendChild(renderMdBlock(textStr));
  return sec;
}

/* 段7 证据来源：表格（类型/ID/出处/等级/原文） */
function renderEvidence(result) {
  var sec = el("section", "section");
  sec.appendChild(sectionTitle("证据来源"));
  var rows = result.evidence || [];
  if (!rows.length) {
    sec.appendChild(el("p", "empty", "（无证据记录）"));
    return sec;
  }
  var table = el("table", "evidence-table");
  var thead = el("thead");
  var headRow = el("tr");
  ["类型", "ID", "出处", "等级", "原文"].forEach(function (h) {
    headRow.appendChild(el("th", "", h));
  });
  thead.appendChild(headRow);
  table.appendChild(thead);
  var tbody = el("tbody");
  rows.forEach(function (row) {
    // 行格式："principle:zhiqi | 自序 | E5 | 原文"
    var parts = String(row).split(" | ", 4);
    var kindId = (parts[0] || "").split(":");
    var tr = el("tr");
    tr.appendChild(el("td", "", kindId[0] || ""));
    tr.appendChild(el("td", "", kindId[1] || ""));
    tr.appendChild(el("td", "", parts[1] || ""));
    tr.appendChild(el("td", "", parts[2] || ""));
    tr.appendChild(el("td", "quote-cell", parts[3] || ""));
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  sec.appendChild(table);
  return sec;
}

/* 容错 JSON 解析：支持 ```json 围栏与首尾杂文；失败返回 null */
function tryParseJson(text) {
  var cleaned = String(text || "").trim();
  if (cleaned.startsWith("```")) {
    var lines = cleaned.split("\n");
    if (lines[0].trim().startsWith("```")) lines.shift();
    if (lines.length && lines[lines.length - 1].trim() === "```") lines.pop();
    cleaned = lines.join("\n").trim();
  }
  var start = cleaned.indexOf("{");
  var end = cleaned.lastIndexOf("}");
  if (start === -1 || end <= start) return null;
  try { return JSON.parse(cleaned.slice(start, end + 1)); } catch (_) { return null; }
}

/* 段8 推演标注：把文本拆为书中依据（深色块）/方法推演（浅色虚线块）。
 * 优先解析 JSON 字符串（LLM 常返回 {"书中依据": [...], "推演": [...]}），
 * 按键名分类；非 JSON 时按段落关键词分类。 */
function classifyAnnotation(text) {
  var parsed = tryParseJson(text);
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    var blocks = [];
    Object.keys(parsed).forEach(function (key) {
      var value = parsed[key];
      if (value === undefined || value === null || value === "") return;
      var type = /推演|外推|推断|推测/.test(key)
        ? "infer"
        : (/书中|依据|原文|出处/.test(key) ? "book" : "neutral");
      var items = Array.isArray(value) ? value : [value];
      var lines = items.map(function (it) {
        return typeof it === "string" ? it : JSON.stringify(it);
      });
      if (lines.length) blocks.push({ type: type, lines: lines });
    });
    if (blocks.length) return blocks;
  }
  var blocks = [];
  var paragraphs = String(text).split(/\n{2,}/)
    .map(function (s) { return s.trim(); }).filter(Boolean);
  paragraphs.forEach(function (para) {
    var type = "neutral";
    // 强标记优先判断：方法外推（非书中原话）> 书中依据
    if (/方法外推|方法推演|非书中|外推/.test(para)) {
      type = "infer";
    } else if (/书中依据|书中有据|书中原话|书中原文|原文依据|出自书中/.test(para)) {
      type = "book";
    } else if (/推演|推断|推测|延伸/.test(para)) {
      type = "infer";
    } else if (/书中|依据|原话/.test(para)) {
      type = "book";
    }
    blocks.push({
      type: type,
      lines: para.split("\n").map(function (s) { return s.trim(); }).filter(Boolean)
    });
  });
  if (!blocks.length) blocks.push({ type: "neutral", lines: ["（无推演标注内容）"] });
  return blocks;
}

function renderAnnotation(result) {
  var sec = el("section", "section");
  sec.appendChild(sectionTitle("推演标注"));

  // 图例：说明两种色块的视觉含义
  var legend = el("div", "annotation-legend");
  legend.appendChild(el("span", "legend-chip book-chip", "深色块 = 书中依据"));
  legend.appendChild(el("span", "legend-chip infer-chip", "浅色虚线块 = 方法推演"));
  sec.appendChild(legend);

  var text = String((result.reasoning || {}).annotation || "");
  classifyAnnotation(text).forEach(function (b) {
    var block = el("div", "annotation-block " + b.type + "-block");
    var label = b.type === "book"
      ? "书中依据"
      : (b.type === "infer" ? "以下为方法外推，非书中原话" : "其他说明");
    block.appendChild(el("div", "annotation-label", label));
    b.lines.forEach(function (line) {
      var p = el("p", "annotation-line");
      p.appendChild(renderInline(line));
      block.appendChild(p);
    });
    sec.appendChild(block);
  });
  return sec;
}

/* 总渲染：8 段依次出现 */
function render(result) {
  var container = document.getElementById("result");
  container.textContent = "";
  container.appendChild(renderQuestion(result));
  container.appendChild(renderDiagnosis(result));
  container.appendChild(renderMethods(result));
  container.appendChild(renderCases(result));
  container.appendChild(renderProse("建议", (result.reasoning || {}).advice));
  container.appendChild(renderProse("例外与风险", (result.reasoning || {}).exceptions));
  container.appendChild(renderEvidence(result));
  container.appendChild(renderAnnotation(result));
  container.classList.remove("hidden");
}

/* ---------- 提交与加载态 ---------- */
function showError(message) {
  var bar = document.getElementById("error-bar");
  bar.textContent = message;
  bar.classList.remove("hidden");
}

function clearError() {
  document.getElementById("error-bar").classList.add("hidden");
}

function setLoading(on) {
  document.getElementById("ask-btn").disabled = on;
  document.getElementById("loading-text").classList.toggle("hidden", !on);
}

async function submitQuestion() {
  var input = document.getElementById("question-input");
  var question = input.value.trim();
  if (!question) {
    showError("请输入问题");
    input.focus();
    return;
  }
  clearError();
  setLoading(true);
  try {
    // 提交任务：立即返回 task_id（异步任务模式，不受网关超时限制）
    var submitResp = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question })
    });
    if (submitResp.status === 401) {
      showError("未授权（401）");
      return;
    }
    var submitData = {};
    try { submitData = await submitResp.json(); } catch (_) { /* 非 JSON 错误体 */ }
    if (!submitResp.ok) {
      showError(submitData.error || "请求失败（" + submitResp.status + "）");
      return;
    }
    var taskId = submitData.task_id;
    if (!taskId) {
      showError("提交失败：未返回任务 ID");
      return;
    }

    // 轮询任务状态（2.5s 间隔，最长 10 分钟）
    var deadline = Date.now() + 10 * 60 * 1000;
    var result = null;
    while (Date.now() < deadline) {
      await new Promise(function (r) { setTimeout(r, 2500); });
      var pollResp = await fetch("/api/task/" + taskId, { cache: "no-store" });
      if (pollResp.status === 401) {
        showError("未授权（401）");
        return;
      }
      var pollData = {};
      try { pollData = await pollResp.json(); } catch (_) { /* 忽略 */ }
      if (pollData.status === "done") { result = pollData.result; break; }
      if (pollData.status === "error") {
        showError(pollData.error || "分析失败，请稍后重试");
        return;
      }
      // pending / running → 继续轮询
    }
    if (!result) {
      showError("分析超时（超过 10 分钟），请重试");
      return;
    }
    render(result);
    document.getElementById("result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (ex) {
    showError("网络错误：" + ex.message);
  } finally {
    setLoading(false);
  }
}

/* ---------- 初始化 ---------- */
document.getElementById("ask-btn").addEventListener("click", submitQuestion);
document.getElementById("question-input").addEventListener("keydown", function (e) {
  // Ctrl/Cmd + Enter 快捷提交（多行输入不拦截普通回车）
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    submitQuestion();
  }
});
