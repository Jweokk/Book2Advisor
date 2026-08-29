# -*- coding: utf-8 -*-
"""
Method Advisor — 8 步推理链主流程。

推理链：
    1. 加载 Method Model（yaml.safe_load）
    2. 问题分类：LLM 从 diagnostics 中选最相关的 1 条（不匹配时按顺序用第一条）
    3. 诊断：把选中的 diagnostic.order 结合用户问题具体化（LLM）
    4. 方法定位：LLM 从 principles 中选 2-5 条、从 rules 中选 1-3 条
    5. 案例检索：LLM 从 cases 中选最相关的 1-3 个
    6. 证据收集：汇总选中 principle/rule 的 evidence[]（quote + loc + level）
    7. 推演：LLM 综合（问题 + 诊断 + 原则 + 规则 + 案例 + 证据）生成建议，
       显式区分「书中依据」与「方法推演」，并给出例外/风险
    8. 输出 Method Trace（Markdown，8 段标题）

约束：
    - 每步 LLM 调用独立 try/except，失败给出明确中文错误并终止（不吞错）
    - --verbose 时打印每步 LLM 调用的输入/输出摘要（不含 API key）
"""

import json
import os
import re
from pathlib import Path

import yaml

from core.runtime.llm import LLMError, extract_json
from core.runtime import prompts

# Method Model 默认路径
# Method Model 路径：必须通过环境变量 METHOD_MODEL 指定（如 /path/to/data/methods/<person>/<model>.yaml）
METHOD_MODEL_PATH = Path(os.environ["METHOD_MODEL"]) if os.environ.get("METHOD_MODEL") else None

# Method Trace 的 8 段标题（测试按此断言）
TRACE_SECTIONS = [
    "## 问题理解",
    "## 诊断路径（按",  # 前缀匹配：build_trace 动态插入 {person_name}先生
    "## 采用的方法（原则 + 规则，逐条带证据引用 [第X章]）",
    "## 相关案例（1-3 个，说明为什么相关）",
    "## 建议",
    "## 例外与风险",
    "## 证据来源（汇总列表：原则/规则 ID + loc + level）",
    "## 推演标注（明确列出：哪些判断有书中依据，哪些是方法推演）",
]


def load_method_model(path: str | Path) -> dict:
    """步骤1：加载 Method Model（yaml.safe_load）。

    METHOD_MODEL 未设置（None）时给出友好提示。
    """
    if path is None:
        raise FileNotFoundError(
            "Method Model 未指定：请设置环境变量 METHOD_MODEL（指向编译好的方法模型 yaml，见 README）"
        )
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Method Model 文件不存在：{path}")
    with path.open(encoding="utf-8") as fh:
        model = yaml.safe_load(fh)
    if not isinstance(model, dict) or "principles" not in model:
        raise ValueError(f"Method Model 结构无效（缺少 principles）：{path}")
    return model


def _guard(step_name: str, fn):
    """包装一步 LLM 调用：失败给出明确中文错误并终止（不吞错）。

    仅捕获 LLMError（llm.py 中已细化的统一异常），不做裸 except。
    """
    try:
        return fn()
    except LLMError as exc:
        raise RuntimeError(f"步骤「{step_name}」LLM 调用失败：{exc}") from exc


def _chat(client, messages, step_label: str, verbose: bool,
          temperature: float = 0.3, max_tokens: int = 2048,
          attempts: int = 2) -> str:
    """调用 LLM；verbose 时打印输入/输出摘要（不含 API key）。

    偶发空响应/不可解析响应是 DeepSeek 的瞬态问题：同一请求自动重试 1 次
    （与指数退避重试互补，指数退避只处理 429/5xx/超时）。
    """
    last_reply = ""
    for attempt in range(attempts):
        if verbose:
            print(f"[{step_label}] LLM 调用（第 {attempt + 1} 次）：")
            for msg in messages:
                content = (msg.get("content") or "")[:200].replace("\n", " ")
                print(f"  输入 {msg.get('role')}: {content}")
        reply = client.chat(messages, temperature=temperature, max_tokens=max_tokens)
        if verbose:
            print(f"  输出: {reply[:300].replace(chr(10), ' ')}")
        if reply and reply.strip():
            return reply
        last_reply = reply
    # 两次都空：交给上层 extract_json 报明确中文错误（不吞错）
    return last_reply


def _select_ids(reply_text: str, key: str, step_label: str) -> list[str]:
    """解析 JSON 中的 id 列表；缺字段或类型错误时给出明确中文错误。"""
    data = extract_json(reply_text)
    if not isinstance(data, dict) or key not in data:
        raise LLMError(f"步骤「{step_label}」返回 JSON 缺少字段「{key}」：{reply_text[:200]}")
    ids = data[key]
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise LLMError(f"步骤「{step_label}」返回「{key}」不是字符串列表：{reply_text[:200]}")
    return ids


# 中文化：实体类型与证据等级显示名
KIND_CN = {"principle": "原则", "rule": "规则", "case": "案例", "diagnostic": "诊断路径"}
LEVEL_CN = {"E5": "极高·多源印证", "E4": "高·原文明确", "E3": "中·案例归纳", "E2": "低·合理推导", "E1": "假设性推演"}


def run_chain(model: dict, question: str, client=None, verbose: bool = False,
             progress_callback=None) -> dict:
    """8 步推理链。progress_callback(step) 每完成一步调用一次（step 形如 "第2/5步·问题分类"）。"""
    """执行 8 步推理链，返回含完整 Method Trace 的结果字典。"""
    from core.runtime.llm import DeepSeekClient
    client = client or DeepSeekClient()
    principles_all: list[dict] = model["principles"]
    rules_all: list[dict] = model.get("rules", [])
    cases_all: list[dict] = model.get("cases", [])
    diagnostics_all: list[dict] = model.get("diagnostics", [])
    _fallback_principle = False
    # 人物名/简介（动态：prompts 与后处理使用，不绑定具体人物）
    def _report(step: str, idx: int) -> None:
        """进度回调（异步任务模式：Web 前端据此显示当前推理步骤）。"""
        if progress_callback:
            progress_callback(f"第{idx}/5步·{step}")

    _pname = model.get("person", {}).get("name", "") if isinstance(model, dict) else ""
    _pbrief = model.get("person", {}).get("brief", "") if isinstance(model, dict) else ""

    # ---------- 步骤2：问题分类 ----------
    def _classify():
        messages = [
            {"role": "system", "content": prompts.classify_system()},
            {"role": "user", "content": prompts.classify_user(question, diagnostics_all)},
        ]
        # 注意：deepseek-v4-flash 为推理模型，思考过程计入 max_tokens 预算，
        # 故各步预算需留足余量，否则会被 finish_reason=length 截断
        reply = _chat(client, messages, "步骤2 问题分类", verbose,
                      temperature=0.1, max_tokens=3000)
        data = extract_json(reply)
        diag_id = data.get("diagnostic_id") if isinstance(data, dict) else None
        if not isinstance(diag_id, str):
            raise LLMError(f"步骤「问题分类」返回缺少 diagnostic_id：{reply[:200]}")
        return {"diagnostic_id": diag_id, "reason": data.get("reason", "")}

    classification = _guard("问题分类", _classify)
    _report("问题分类", 1)
    # 中文化：诊断路径显示名（保留 diagnostic_id 作内部引用）
    _diag = next(
        (d for d in diagnostics_all if d["id"] == classification["diagnostic_id"]), None
    )
    classification["name"] = (_diag or {}).get("name") or classification["diagnostic_id"]

    # 选中的诊断路径：按 id 匹配；不匹配时按顺序用第一条
    diagnostic = next(
        (d for d in diagnostics_all if d["id"] == classification["diagnostic_id"]),
        diagnostics_all[0] if diagnostics_all else {"id": "", "order": ["先了解情况再作判断"]},
    )
    if diagnostic["id"] != classification["diagnostic_id"]:
        classification["fallback"] = True

    # 泛问/概念讨论分支标志（classify 输出 GENERAL_QA 时走引导回复，不套经营原则）
    _is_general = classification["diagnostic_id"] == "GENERAL_QA"

    # ---------- 步骤3：诊断具体化 ----------
    if _is_general:
        diagnosis = (f"该问题属于泛问/概念讨论/闲聊，不是具体的经营决策场景。"
                     f"{_pname}的方法论针对经营与处世决策，需要具体场景才能给出有价值的分析。")
    else:
        def _diagnose():
            messages = [
                {"role": "system", "content": prompts.diagnose_system(_pname, _pbrief)},
                {"role": "user", "content": prompts.diagnose_user(question, diagnostic)},
            ]
            return _chat(client, messages, "步骤3 诊断", verbose,
                         temperature=0.4, max_tokens=2000).strip()

        diagnosis = _guard("诊断", _diagnose)
    _report("诊断具体化", 2)

    # ---------- 步骤4：方法定位 ----------
    if _is_general:
        p_ids, r_ids = [], []
    else:
        def _select_method():
            messages = [
                {"role": "system", "content": prompts.select_method_system(_pname)},
                {"role": "user", "content": prompts.select_method_user(
                    question, diagnosis, principles_all, rules_all)},
            ]
            reply = _chat(client, messages, "步骤4 方法定位", verbose,
                          temperature=0.1, max_tokens=6000)
            p_ids = _select_ids(reply, "principles", "方法定位")
            r_ids = _select_ids(reply, "rules", "方法定位")
            return p_ids, r_ids

        p_ids, r_ids = _guard("方法定位", _select_method)
    _report("方法定位", 3)

    # 过滤出模型中的完整对象（防御无效 id：LLM 幻觉出的 id 直接丢弃）
    selected_principles = [p for p in principles_all if p["id"] in p_ids][:5]
    selected_rules = [r for r in rules_all if r["id"] in r_ids][:3]
    # 允许「宁缺毋滥」：原则可为空（只靠规则回答）；但原则与规则都为空时，
    # 降级为第一条原则兜底并标注（避免 500——用户问超出方法论覆盖范围的问题时也要有回答）
    # ⚠️ 泛问分支（GENERAL_QA）除外：明确走引导回复，不兜底、不套原则
    if not selected_principles and not selected_rules:
        if _is_general:
            pass
        elif principles_all:
            selected_principles = [principles_all[0]]
            _fallback_principle = True
        else:
            raise RuntimeError("Method Model 无任何原则，无法回答")

    # ---------- 步骤5：案例检索 ----------
    if _is_general:
        c_ids = []
    else:
        def _select_cases():
            messages = [
                {"role": "system", "content": prompts.select_cases_system(_pname)},
                {"role": "user", "content": prompts.select_cases_user(
                    question, diagnosis, [p["id"] for p in selected_principles], cases_all)},
            ]
            reply = _chat(client, messages, "步骤5 案例检索", verbose,
                          temperature=0.1, max_tokens=3000)
            return _select_ids(reply, "cases", "案例检索")

        c_ids = _guard("案例检索", _select_cases)
    _report("案例检索", 4)
    selected_cases = [c for c in cases_all if c["id"] in c_ids][:3]

    # ---------- 步骤6：证据收集（纯代码，汇总选中 principle/rule 的 evidence[]） ----------
    evidence_rows: list[str] = []
    for kind, items in (("principle", selected_principles), ("rule", selected_rules)):
        for item in items:
            for ev in item.get("evidence", []):
                evidence_rows.append(
                    f"{KIND_CN.get(kind, kind)}:{item.get('name', item['id'])}"
                    f" | {ev.get('loc', '')} | {LEVEL_CN.get(ev.get('level', ''), ev.get('level', ''))}"
                    f" | {ev.get('quote', '')}"
                )

    # ---------- 步骤7：推演 ----------
    def _to_text(v) -> str:
        """LLM 输出格式漂移防御：字段可能是嵌套 dict/list（如 annotation 被返回成对象），统一转文本。"""
        if isinstance(v, str):
            return v.strip()
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    if _is_general:
        # 泛问引导：不调用具体原则/规则/案例，识别泛问并引导用户给具体场景
        def _general_reply():
            messages = [
                {"role": "system", "content": prompts.general_qa_system(_pname, _pbrief)},
                {"role": "user", "content": prompts.general_qa_user(question, diagnosis)},
            ]
            reply = _chat(client, messages, "步骤7b 泛问引导", verbose,
                          temperature=0.4, max_tokens=8000)
            data = extract_json(reply)
            missing = [k for k in ("advice", "exceptions", "annotation") if not data.get(k)]
            if missing:
                raise LLMError(f"步骤「泛问引导」返回 JSON 缺少字段 {missing}：{reply[:200]}")
            return {"advice": _to_text(data["advice"]),
                    "exceptions": _to_text(data["exceptions"]),
                    "annotation": _to_text(data["annotation"])}

        reasoning = _guard("泛问引导", _general_reply)
        _report("推演", 5)
    else:
        def _reason():
            messages = [
                {"role": "system", "content": prompts.reason_system(_pname, _pbrief)},
                {"role": "user", "content": prompts.reason_user(
                    question, diagnosis, _pname, selected_principles, selected_rules,
                    selected_cases, evidence_rows)},
            ]
            # 推演输出很长，LLM 偶发 JSON 格式错误（截断/多余逗号）——重试 1 次
            last_exc = None
            for attempt in range(2):
                try:
                    reply = _chat(client, messages, "步骤7 推演", verbose,
                                  temperature=0.4, max_tokens=16000)
                    data = extract_json(reply)
                    break
                except LLMError as exc:
                    last_exc = exc
                    if attempt == 0:
                        continue
                    raise
            else:
                raise last_exc or LLMError("步骤「推演」LLM 调用连续失败，无可用错误信息")  # 理论上不可达
            missing = [k for k in ("advice", "exceptions", "annotation") if not data.get(k)]
            if missing:
                raise LLMError(f"步骤「推演」返回 JSON 缺少字段 {missing}：{reply[:200]}")
            return {"advice": _to_text(data["advice"]),
                    "exceptions": _to_text(data["exceptions"]),
                    "annotation": _to_text(data["annotation"])}

        reasoning = _guard("推演", _reason)
        _report("推演", 5)

    # ---------- 步骤7.5：输出中文化后处理 ----------
    # 1) LLM 引用的是英文 id → 替换为中文名（推演标注/建议中的 jujiao、r-standard-conflict 等）
    # 2) 人物名 → "XX先生"（动态）
    id2name = {
        **{p["id"]: p.get("name", p["id"]) for p in principles_all},
        **{r["id"]: r.get("name", r["id"]) for r in rules_all},
        **{c["id"]: c.get("name", c["id"]) for c in cases_all},
        **{d["id"]: d.get("name", d["id"]) for d in diagnostics_all},
    }
    _pname2 = model.get("person", {}).get("name", "") if isinstance(model, dict) else ""

    def _cn_post(t: str) -> str:
        if not isinstance(t, str):
            return t
        t2 = t.replace("principle:", "原则：").replace("rule:", "规则：").replace("case:", "案例：")
        for i, n in sorted(id2name.items(), key=lambda kv: -len(kv[0])):
            if i != n:
                t2 = re.sub(rf"\b{re.escape(i)}\b", n, t2)
        if _pname2:
            t2 = re.sub(rf"{re.escape(_pname2)}(?!先生)", f"{_pname2}先生", t2)
        return t2
    reasoning = {k: _cn_post(v) for k, v in reasoning.items()}
    diagnosis = _cn_post(diagnosis)
    if isinstance(classification.get("reason"), str):
        classification["reason"] = _cn_post(classification["reason"])

    _person_name = _pname

    # ---------- 步骤8：输出 Method Trace（Markdown，8 段） ----------
    trace = build_trace(question, _person_name, classification, diagnostic, diagnosis,
                        selected_principles, selected_rules, selected_cases,
                        evidence_rows, reasoning, fallback_principle=_fallback_principle)
    return {
        "question": question,
        "classification": classification,
        "diagnostic": diagnostic,
        "diagnosis": diagnosis,
        "principles": selected_principles,
        "rules": selected_rules,
        "cases": selected_cases,
        "evidence": evidence_rows,
        "reasoning": reasoning,
        "trace": trace,
        "fallback_principle": _fallback_principle,
    }


def _fmt_evidence(evidence: list[dict]) -> str:
    """把 evidence[] 格式化为「quote」[loc]（E level）引用串。"""
    parts = []
    for ev in evidence:
        loc = ev.get("loc", "")
        level = ev.get("level", "")
        tag = f"[{loc}]" if loc else ""
        if level:
            level_cn = LEVEL_CN.get(level, level)
            tag = f"{tag}（{level_cn}）" if tag else f"（{level_cn}）"
        parts.append(f"「{ev.get('quote', '')}」{tag}")
    return "；".join(parts) or "（无直接引文）"


def build_trace(question: str, person_name: str, classification: dict, diagnostic: dict,
                diagnosis: str, principles: list[dict], rules: list[dict],
                cases: list[dict], evidence_rows: list[str],
                reasoning: dict, fallback_principle: bool = False) -> str:
    """组装 8 段 Method Trace（Markdown）。"""
    parts: list[str] = []

    # 段1：问题理解
    parts.append("## 问题理解")
    parts.append(f"- 问题：{question}")
    parts.append(f"- 问题分类：{classification.get('name', classification.get('diagnostic_id', ''))}"
                 f"（{classification.get('reason', '')}）")
    if classification.get("fallback"):
        parts.append("- 说明：问题与现有诊断路径均不完全匹配，已按顺序采用第一条诊断路径。")

    # 段2：诊断路径
    parts.append(f"## 诊断路径（按{person_name}先生的方法，先看什么）")
    parts.append(diagnosis)

    # 段3：采用的方法（原则 + 规则，逐条带证据引用 [第X章]）
    parts.append("## 采用的方法（原则 + 规则，逐条带证据引用 [第X章]）")
    if fallback_principle:
        parts.append(f"> ⚠️ 说明：该问题与{person_name}先生方法论的核心适用场景匹配度较低，以下为最接近的原则作参考，建议谨慎套用。")
    parts.append("**原则：**")
    if not principles:
        parts.append("（本问题未触发任何原则——宁缺毋滥，仅按规则判断）")
    for p in principles:
        parts.append(f"- **{p.get('name', p['id'])}**：{p['statement']}")
        trig = p.get("trigger")
        if isinstance(trig, dict) and (trig.get("scenes") or trig.get("signals")):
            scenes = "；".join(trig.get("scenes") or [])
            signals = "、".join(trig.get("signals") or [])
            note = []
            if scenes:
                note.append(f"触发场景：{scenes}")
            if signals:
                note.append(f"信号词：{signals}")
            parts.append(f"  - 命中依据：{' ｜ '.join(note)}")
        parts.append(f"  - 证据：{_fmt_evidence(p.get('evidence', []))}")
    if rules:
        parts.append("**规则：**")
        for r in rules:
            triggers = "；".join(r.get("trigger", []))
            decisions = "；".join(
                f"{k}→{v}" for k, v in (r.get("decisions") or {}).items()
            )
            parts.append(f"- **{r.get('name', r['id'])}**：触发条件「{triggers}」")
            if decisions:
                parts.append(f"  - 决策：{decisions}")
            parts.append(f"  - 证据：{_fmt_evidence(r.get('evidence', []))}")
    else:
        parts.append("（本问题未触发任何规则）")

    # 段4：相关案例
    parts.append("## 相关案例（1-3 个，说明为什么相关）")
    if cases:
        for c in cases:
            parts.append(f"- **{c.get('name', c['id'])}**：问题「{c['problem']}」")
            parts.append(f"  - 决策：{c['decision']}")
            parts.append(f"  - 结果：{c['outcome']}")
    else:
        parts.append("（未检索到高度相关案例）")

    # 段5：建议
    parts.append("## 建议")
    parts.append(reasoning["advice"])

    # 段6：例外与风险
    parts.append("## 例外与风险")
    parts.append(reasoning["exceptions"])

    # 段7：证据来源（汇总列表：原则/规则 ID + loc + level）
    parts.append("## 证据来源（汇总列表：原则/规则 ID + loc + level）")
    parts.append("| 类型 | ID | 出处 | 等级 | 原文 |")
    parts.append("| --- | --- | --- | --- | --- |")
    for row in evidence_rows:
        kind_id, loc, level, quote = row.split(" | ", 3)
        parts.append(f"| {kind_id.split(':')[0]} | {kind_id.split(':')[1]} | {loc} | {level} | {quote} |")

    # 段8：推演标注
    parts.append("## 推演标注（明确列出：哪些判断有书中依据，哪些是方法推演）")
    parts.append(reasoning["annotation"])

    return "\n\n".join(parts)
