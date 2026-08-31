#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""方法模型 → 人物咨询 Skill 导出器（纯模板渲染，无 LLM 调用）。

把已编译并通过 schema 校验的方法模型（yaml）渲染为 agent 可加载的 skill：

    <person>-skill/
      SKILL.md                  frontmatter + 人物身份 + 咨询流程 + 核心方法 + 索引
      references/principles.md    全部原则（trigger 触发场景 + 证据链）
      references/rules.md         规则（trigger / decisions / exceptions）
      references/cases.md         案例
      references/diagnostics.md   诊断路径 + 观点张力 + 思想演变

用法:
    python3 scripts/export_skill.py \\
        --model data/methods/<person>/<model>.yaml \\
        --out ~/.claude/skills/<person>-method

安装位置（任选宿主，格式通用）:
    Claude Code:  ~/.claude/skills/<name>/
    Hermes:       ~/.hermes/skills/<name>/
    Copilot CLI:  ~/.copilot/skills/<name>/
    Agent 通用:   ~/.agents/skills/<name>/

产物特点：SKILL.md 保持精简（咨询流程 + 索引），细节按需加载（references/），
引用/推演强制分离、越界诚实等约束写死在流程模板中（templates/advisor-skill-flow.md）。
"""
import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOW_TEMPLATE = PROJECT_ROOT / "templates" / "advisor-skill-flow.md"
MAX_DESC = 1024  # frontmatter description 上限（Claude Code 规范）

# ---------- 渲染工具 ----------

def _lines(out: list[str], *texts: str) -> None:
    for t in texts:
        out.append(t)


def _fmt_evidence(ev: dict) -> str:
    q = ev.get("quote", "").replace("\n", " ")
    loc = ev.get("loc", "")
    lv = ev.get("level", "")
    return f"  - 原文：{q}（出处：{loc}，证据级别 {lv}）"


def _fmt_trigger(trig: dict) -> str:
    lines = []
    if trig.get("scenes"):
        lines.append("  适用场景：" + "；".join(trig["scenes"]))
    if trig.get("signals"):
        lines.append("  触发信号：" + "；".join(trig["signals"]))
    if trig.get("not_for"):
        lines.append("  不应触发：" + "；".join(trig["not_for"]))
    return "\n".join(lines)


def build_description(model: dict) -> str:
    """frontmatter description：触发判断用（agent 靠它决定何时加载本 skill）。"""
    p = model.get("person", {})
    name = p.get("name", "")
    domain = p.get("domain", "")
    brief = p.get("brief", "")
    pnames = [x.get("name", "") for x in model.get("principles", [])][:8]
    desc = (
        f"{name}（{domain}）的方法论顾问。"
        f"Use when the user asks how {name} would view/decide/handle a business "
        f"or life decision, wants analysis in {name}'s methodology"
        + (f"（{'、'.join(pnames)}）" if pnames else "")
        + f"，or consults their principles on {domain}。"
    )
    if brief:
        desc += f" 人物背景：{brief}"
    return desc[:MAX_DESC]


def render_skill_md(model: dict, flow_text: str) -> str:
    """SKILL.md 主文件：frontmatter + 身份 + 流程 + 核心方法 + 索引。"""
    p = model.get("person", {})
    name = p.get("name", "")
    out: list[str] = []
    _lines(out,
           "---",
           f'name: {p.get("id", "person")}-method',
           f'description: "{build_description(model).replace(chr(34), chr(39))}"',
           "---",
           "",
           f"# {name}方法论顾问",
           "",
           f"> 基于 {name} 的书/文章/演讲/访谈编译的人物方法模型。"
           "回答遵循「书中依据 vs 方法推演」强制分离，杜绝幻觉引用。",
           "",
           f"## 人物背景",
           "",
           f"- **领域**：{p.get('domain', '')}",
           f"- **简介**：{p.get('brief', '')}",
           "",
           "## 何时使用本 skill",
           "",
           "当用户的问题涉及：")
    scenes = []
    for pr in model.get("principles", []):
        for s in (pr.get("trigger", {}) or {}).get("scenes", []):
            if s not in scenes:
                scenes.append(s)
    for s in scenes[:12]:
        out.append(f"- {s}")
    _lines(out,
           "",
           "不匹配时不要强行调用本 skill。",
           "",
           "## 咨询流程",
           "",
           flow_text,
           "",
           "## 核心方法速览",
           "")
    for pr in model.get("principles", []):
        out.append(f"- **{pr.get('name', '')}**：{pr.get('statement', '')}")
    _lines(out,
           "",
           "## 索引（细节按需加载）",
           "",
           "| 文件 | 内容 | 何时读取 |",
           "|---|---|---|",
           "| `references/principles.md` | 全部原则 + 触发场景 + 证据链 | 第 2 步方法定位时 |",
           "| `references/rules.md` | 规则（触发条件/决策/例外） | 第 2 步匹配规则时 |",
           "| `references/cases.md` | 案例（背景/决策/结果） | 需要举例佐证时 |",
           "| `references/diagnostics.md` | 诊断路径 + 观点张力 + 思想演变 | 第 1 步诊断时 |",
           "")
    return "\n".join(out)


def render_principles(model: dict) -> str:
    out: list[str] = ["# 原则（含触发场景与证据链）", "",
                      "> 引用必须附原文证据（quote + loc）；trigger.not_for 场景禁止调用。", ""]
    for pr in model.get("principles", []):
        out.append(f"## {pr.get('name', '')}（`{pr.get('id', '')}`）")
        out.append("")
        out.append(f"{pr.get('statement', '')}")
        out.append(f"- 置信度：{pr.get('confidence', '')}")
        trig = pr.get("trigger", {})
        if trig:
            out.append(_fmt_trigger(trig))
        if pr.get("evidence"):
            out.append("- 证据：")
            for ev in pr["evidence"]:
                out.append(_fmt_evidence(ev))
        out.append("")
    return "\n".join(out)


def render_rules(model: dict) -> str:
    out: list[str] = ["# 规则", "", "> 触发条件命中时执行对应决策；exceptions 列出的情况例外。", ""]
    for r in model.get("rules", []):
        out.append(f"## {r.get('name', '')}（`{r.get('id', '')}`）")
        out.append("")
        if r.get("trigger"):
            out.append("- 触发条件：" + "；".join(r["trigger"]))
        if r.get("diagnose"):
            out.append("- 诊断维度：" + "；".join(r["diagnose"]))
        if r.get("decisions"):
            out.append("- 决策映射：")
            for k, v in r["decisions"].items():
                out.append(f"  - {k} → {v}")
        if r.get("exceptions"):
            out.append("- 例外：" + "；".join(r["exceptions"]))
        if r.get("evidence"):
            out.append("- 证据：")
            for ev in r["evidence"]:
                out.append(_fmt_evidence(ev))
        out.append("")
    return "\n".join(out)


def render_cases(model: dict) -> str:
    out: list[str] = ["# 案例", ""]
    for c in model.get("cases", []):
        out.append(f"## {c.get('name', '')}（`{c.get('id', '')}`）")
        out.append("")
        for k, label in (("context", "背景"), ("problem", "问题"), ("decision", "决策"),
                         ("action", "行动"), ("outcome", "结果"), ("reasoning", "推理")):
            if c.get(k):
                out.append(f"- {label}：{c[k]}")
        if c.get("principle"):
            out.append("- 对应原则：" + "、".join(c["principle"]))
        if c.get("evidence"):
            out.append("- 证据：")
            for ev in c["evidence"]:
                out.append(_fmt_evidence(ev))
        out.append("")
    return "\n".join(out)


def render_diagnostics(model: dict) -> str:
    out: list[str] = ["# 诊断路径 / 观点张力 / 思想演变", ""]
    out.append("## 诊断路径")
    out.append("")
    for d in model.get("diagnostics", []):
        out.append(f"### {d.get('name', '')}（`{d.get('id', '')}`）")
        steps = d.get("order", [])
        for i, s in enumerate(steps, 1):
            out.append(f"{i}. {s}")
        out.append("")
    if model.get("tensions"):
        out.append("## 观点张力（同一问题的不同侧重点）")
        out.append("")
        for t in model["tensions"]:
            a = t.get("a", ""); b = t.get("b", "")
            out.append(f"- **{a}** ↔ **{b}**")
            if t.get("when_a"):
                out.append(f"  - 倾向 {a} 时：{t['when_a']}")
            if t.get("when_b"):
                out.append(f"  - 倾向 {b} 时：{t['when_b']}")
        out.append("")
    if model.get("evolution"):
        out.append("## 思想演变（按时期回答，不平铺矛盾）")
        out.append("")
        for e in model["evolution"]:
            out.append(f"### {e.get('period', '')}")
            if e.get("date_before"):
                out.append(f"- {e['date_before']}：{e.get('notes', '')}")
            elif e.get("notes"):
                out.append(f"- {e['notes']}")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="方法模型 → 人物咨询 Skill 导出器")
    ap.add_argument("--model", required=True, help="方法模型 yaml 路径")
    ap.add_argument("--out", required=True, help="输出 skill 目录（如 ~/.claude/skills/<person>-method）")
    args = ap.parse_args()

    model_path = Path(args.model)
    if not model_path.is_file():
        sys.exit(f"错误：方法模型不存在：{model_path}")
    with model_path.open(encoding="utf-8") as fh:
        model = yaml.safe_load(fh)
    if not isinstance(model, dict) or not model.get("person") or "principles" not in model:
        sys.exit("错误：模型结构无效（缺少 person 或 principles）——请先通过 validate_schema.py 校验")

    # 建议先校验（不强制阻断，但提示）
    import subprocess
    r = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "validate_schema.py"), str(model_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("⚠️ 提示：模型未通过 validate_schema.py 校验，导出产物可能不完整。", flush=True)
        print(r.stdout.strip()[-300:], flush=True)

    flow = FLOW_TEMPLATE.read_text(encoding="utf-8")
    # 只取模板正文（"## 咨询流程" 之后），跳过模板说明头
    flow = flow[flow.find("## 咨询流程"):]
    pname = model["person"].get("name", "")
    flow = flow.replace("{{PERSON_NAME}}", pname)

    out_dir = Path(args.out)
    ref_dir = out_dir / "references"
    ref_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "SKILL.md").write_text(render_skill_md(model, flow), encoding="utf-8")
    (ref_dir / "principles.md").write_text(render_principles(model), encoding="utf-8")
    (ref_dir / "rules.md").write_text(render_rules(model), encoding="utf-8")
    (ref_dir / "cases.md").write_text(render_cases(model), encoding="utf-8")
    (ref_dir / "diagnostics.md").write_text(render_diagnostics(model), encoding="utf-8")

    n = (len(model.get("principles", [])), len(model.get("rules", [])),
         len(model.get("cases", [])), len(model.get("diagnostics", [])))
    print(f"✅ 导出完成：{out_dir}")
    print(f"   原则 {n[0]} / 规则 {n[1]} / 案例 {n[2]} / 诊断 {n[3]}")
    print("   安装：把该目录复制到 ~/.claude/skills/ 或 ~/.hermes/skills/ 等（见 docs/SKILL-EXPORT.md）")


if __name__ == "__main__":
    main()
