# -*- coding: utf-8 -*-
"""
Method Advisor — LLM prompt 模板集中地（TASK-P4 硬性约束：模板禁止散落硬编码）。

覆盖 8 步推理链中 5 次 LLM 调用：
    步骤2 问题分类     → classify_system / classify_user
    步骤3 诊断具体化   → diagnose_system / diagnose_user
    步骤4 方法定位     → select_method_system / select_method_user
    步骤5 案例检索     → select_cases_system / select_cases_user
    步骤7 方法推演     → reason_system / reason_user
"""


# ---------- 步骤2：问题分类（从 diagnostics 中选最相关的 1 条） ----------

def classify_system() -> str:
    return (
        "你是 Method Advisor 的问题分类器。给定用户问题与候选人诊断路径列表，"
        "判断该问题最匹配哪一条诊断路径。"
        "只输出 JSON，格式：{\"diagnostic_id\": \"<id>\", \"reason\": \"<30字内理由>\"}。"
    )


def classify_user(question: str, diagnostics: list[dict]) -> str:
    lines = []
    for idx, diag in enumerate(diagnostics, start=1):
        steps = "\n".join(f"      {i}. {s}" for i, s in enumerate(diag["order"], start=1))
        lines.append(f"  {idx}. {diag['id']}：\n{steps}")
    return (
        f"用户问题：{question}\n\n"
        f"候选人诊断路径（id → 步骤）：\n" + "\n".join(lines) +
        "\n\n要求：按问题内容与每条路径的适配度选出最相关的 1 条；"
        "若均不匹配，则选第 1 条并在 reason 中说明。"
    )


# ---------- 步骤3：诊断具体化（把选中的 diagnostic.order 结合问题展开） ----------

def diagnose_system(person_name: str, person_brief: str = "") -> str:
    desc = f"（{person_brief}）" if person_brief else ""
    return (
        f"你是{person_name}{desc}的方法顾问。"
        "下面给出一条诊断路径（诊断顺序）。请结合用户的具体问题，把这条诊断路径"
        "具体化为针对该问题的诊断说明：先看什么、怎么验证、可能出现哪几种情况、"
        "如何对症下药。用 200-350 字中文，条理清晰，直接输出诊断说明正文。"
    )


def diagnose_user(question: str, diagnostic: dict) -> str:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(diagnostic["order"], start=1))
    return f"用户问题：{question}\n\n诊断路径（{diagnostic['id']}）：\n{steps}"


# ---------- 步骤4：方法定位（principles 选 2-5 条，rules 选 1-3 条） ----------

def select_method_system(person_name: str) -> str:
    return (
        f"你是{person_name}方法顾问。根据用户问题与诊断结果，从给定的原则（principles）中"
        "选出最适用的 1-5 条，从规则（rules）中选出最适用的 0-3 条。\n"
        "选择标准（按优先级）：\n"
        "① 原则的 trigger 触发场景/信号词与用户问题有明确对应（首选依据）；\n"
        "② statement 与问题的语义匹配；\n"
        "③ 若问题的场景落在某原则的 not_for 中，则禁止选择该原则。\n"
        "硬性规则：\n"
        "- 宁缺毋滥：没有明确触发的原则就不要选，允许只选 1 条甚至不选原则（只选规则）。\n"
        "- 禁止「万能原则」：如果某原则只是字面上沾边（如名字里带'勤''诚''心'等），"
        "但触发场景并未被用户问题命中，绝不选它。\n"
        "- 每条选中的原则，其 scenes/signals 必须能在用户问题里找到对应痕迹。\n"
        "只输出 JSON，格式：{\"principles\": [\"<id>\", ...], \"rules\": [\"<id>\", ...]}。"
    )


def select_method_user(question: str, diagnosis: str,
                       principles: list[dict], rules: list[dict]) -> str:
    p_lines = []
    for p in principles:
        line = f"  - {p['id']}：{p['statement']}"
        trig = p.get("trigger")
        if isinstance(trig, dict):
            scenes = trig.get("scenes") or []
            signals = trig.get("signals") or []
            not_for = trig.get("not_for") or []
            extra = []
            if scenes:
                extra.append("触发场景: " + "；".join(scenes))
            if signals:
                extra.append("信号词: " + "、".join(signals))
            if not_for:
                extra.append("不应误用于: " + "；".join(not_for))
            if extra:
                line += " ｜ " + " ｜ ".join(extra)
        p_lines.append(line)
    r_lines = "\n".join(
        f"  - {r['id']}：触发条件 → {'；'.join(r['trigger'])}" for r in rules
    )
    return (
        f"用户问题：{question}\n\n诊断结果：{diagnosis}\n\n"
        f"原则列表（id：statement ｜ trigger）：\n{p_lines}\n\n"
        f"规则列表（id：触发条件）：\n{r_lines}\n\n"
        f"要求：principles 选 1-5 条（宁缺毋滥，未命中 trigger 的不选），rules 选 0-3 条，只输出 JSON。"
    )


# ---------- 步骤5：案例检索（cases 选 1-3 个，按 problem 相似度） ----------

def select_cases_system(person_name: str) -> str:
    return (
        f"你是{person_name}方法顾问。根据用户问题、诊断结果与已选原则，从案例库中选出"
        "最相关的 1-3 个案例（按 problem 与用户问题的相似度）。"
        "只输出 JSON，格式：{\"cases\": [\"<id>\", ...]}。"
    )


def select_cases_user(question: str, diagnosis: str,
                      principle_ids: list[str], cases: list[dict]) -> str:
    c_lines = "\n".join(f"  - {c['id']}：问题「{c['problem']}」→ 决策「{c['decision']}」" for c in cases)
    return (
        f"用户问题：{question}\n\n诊断结果：{diagnosis}\n\n"
        f"已选原则：{', '.join(principle_ids)}\n\n"
        f"案例库（id：问题 → 决策）：\n{c_lines}\n\n"
        f"要求：选 1-3 个最相关案例，只输出 JSON。"
    )


# ---------- 步骤7：方法推演（综合所有上下文生成建议，显式区分依据与推演） ----------

def reason_system(person_name: str, person_brief: str = "") -> str:
    desc = f"（{person_brief}）" if person_brief else ""
    return (
        f"你是{person_name}{desc}的方法顾问。"
        f"请严格按{person_name}的方法逻辑对用户问题作推演：先摆依据、再推演、后给建议。"
        "只输出 JSON，包含三个字段：\n"
        "1. advice：具体建议（按人物方法逻辑推理，400-700 字中文，可分条）；\n"
        "2. exceptions：例外与风险（哪些情况下该建议不适用、存在什么风险，150-300 字）；\n"
        "3. annotation：推演标注——明确区分两类内容：①有书中依据的判断（引用原则/规则 ID 与原文证据，标注为「书中依据」）；"
        "②基于方法逻辑的外推（标注为「推演」）。必须同时包含「书中依据」与「推演」两类内容。\n"
        "只输出 JSON，不要输出其他任何文字。"
    )


def reason_user(question: str, diagnosis: str, person_name: str,
                principles: list[dict], rules: list[dict],
                cases: list[dict], evidence_rows: list[str]) -> str:
    # 原则/规则只列 id + statement（证据原文已在 evidence_rows 汇总，避免重复塞入拖慢推演）
    p_lines = [f"  - {p['id']}：{p['statement']}" for p in principles]
    r_lines = []
    for r in rules:
        decisions = "；".join(
            f"{k}→{v}" for k, v in (r.get("decisions") or {}).items()
        )
        r_lines.append(f"  - {r['id']}：触发={'；'.join(r['trigger'])}；决策={decisions}")
    c_lines = []
    for c in cases:
        c_lines.append(f"  - {c['id']}：问题「{c['problem']}」→ 决策「{c['decision']}」→ 结果「{c['outcome']}」")
    ev_lines = "\n".join(f"  - {row}" for row in evidence_rows)
    return (
        f"用户问题：{question}\n\n"
        f"诊断结果：{diagnosis}\n\n"
        f"采用的原则（id：statement）：\n" + "\n".join(p_lines) + "\n\n"
        f"采用的规则（id：触发/决策）：\n" + "\n".join(r_lines) + "\n\n"
        f"相关案例（id：问题 → 决策 → 结果）：\n" + "\n".join(c_lines) + "\n\n"
        f"证据汇总（ID | 出处 | 等级 | 原文）：\n{ev_lines}\n\n"
        f"要求：严格按{person_name}的方法逻辑推演；在 annotation 中显式区分「书中依据」与「推演」；"
        f"在 exceptions 中给出例外与风险。"
    )
