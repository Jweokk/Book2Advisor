#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_triggers.py — 为 Method Model 的每条 principle 生成 trigger 初稿（基于触发场景设计）。

用法:
    python3 scripts/gen_triggers.py --model <yaml路径> [--out <输出路径>] [--dry-run]

输入: 每条 principle 的 name / statement / evidence[0].quote
输出: {principle_id: {scenes: [...], signals: [...], not_for: [...]}} 写入 <model>.triggers.yaml
      不直接改主文件，人工核对后合并。

设计要点:
- scenes: 用户在什么情境下会问到这个原则（3 条，具体到可识别的情况）
- signals: 用户话里的典型信号词（3-6 个，含中文；对英文提问场景可加英文词）
- not_for: 不应误触发的情况（1-2 条，防吸铁石原则乱入，如"资源分配排序"对"天道酬勤"）
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from core.runtime.llm import DeepSeekClient, extract_json

SYSTEM = """你是方法论顾问模型的数据工程师。为给定的每一条「人物原则」设计 trigger 触发场景。

原则来自人物方法论模型（如目标人物《心若菩提》、另一人物讲话）。你的任务：为每条原则写清楚「什么时候该用、什么时候不该用」，让顾问回答问题时能精确匹配正确原则。

输出要求（严格 JSON）：
{
  "<principle_id>": {
    "scenes": ["用户会在什么情境下问到这个原则 — 3条，具体到可识别的情况"],
    "signals": ["用户话里的典型信号词 — 3-6个，中文为主"],
    "not_for": ["不应误触发的情况 — 1-2条，指出哪些表面相关但实际不该用此原则的场景"]
  }
}

设计准则：
1. scenes 必须具体：不是"做决策时"这种废话，而是"行业产能过剩、同行砸盘时"
2. signals 是用户可能说出的词/短语，如"产能过剩""砸盘""价格战"
3. not_for 特别重要：防止原则变成"万能吸铁石"——明确写出哪些场景虽然沾边但不应调用
4. 每一条原则单独判断，不重复
只输出 JSON，不要任何其他文字。"""


def build_user(principles: list[dict]) -> str:
    lines = []
    for p in principles:
        name = p.get("name", p["id"])
        stmt = p.get("statement", "")
        ev = (p.get("evidence") or [{}])[0].get("quote", "")
        lines.append(f"### {p['id']}（{name}）\n陈述：{stmt}\n代表引文：{ev}")
    return "以下是全部原则，请为每条生成 trigger：\n\n" + "\n\n".join(lines)


def gen_triggers(model_path: Path, out_path: Path, dry_run: bool = False) -> int:
    with model_path.open(encoding="utf-8") as fh:
        model = yaml.safe_load(fh)
    principles = model.get("principles", [])
    if not principles:
        print(f"错误：{model_path} 没有 principles")
        return 1
    print(f"模型: {model_path.name} | 原则数: {len(principles)} | dry_run={dry_run}")

    if dry_run:
        for p in principles:
            print(f"  - {p['id']} ({p.get('name', '')}): {p.get('statement', '')[:40]}...")
        print("dry-run 结束，未调用 LLM。")
        return 0

    client = DeepSeekClient()
    # 分批（每批 6 条），避免单次输出过长被截断
    batch_size = 6
    all_triggers: dict = {}
    for i in range(0, len(principles), batch_size):
        batch = principles[i:i + batch_size]
        user_msg = build_user(batch)
        ok = False
        for attempt in range(3):
            try:
                reply = client.chat(
                    [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.2,
                    max_tokens=6000,
                )
                data = extract_json(reply)
                if not isinstance(data, dict):
                    raise ValueError("返回不是 JSON 对象")
                all_triggers.update(data)
                print(f"  批次 {i // batch_size + 1} 完成（{len(data)} 条）")
                ok = True
                break
            except Exception as exc:
                print(f"  批次 {i // batch_size + 1} 第 {attempt + 1} 次失败: {str(exc)[:120]}")
                time.sleep(2)
        if not ok:
            print(f"错误：批次 {i // batch_size + 1} 三次重试仍失败，中止。")
            return 1

    # 校验完整性：每个 principle 都有 trigger
    missing = [p["id"] for p in principles if p["id"] not in all_triggers]
    if missing:
        print(f"警告：以下原则缺少 trigger: {missing}")

    with out_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(all_triggers, fh, allow_unicode=True, sort_keys=False)
    print(f"已写入: {out_path}（{len(all_triggers)} 条）")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Method Model yaml 路径")
    ap.add_argument("--out", default=None, help="trigger 输出路径（默认 <model>.triggers.yaml）")
    ap.add_argument("--dry-run", action="store_true", help="只列原则不调用 LLM")
    args = ap.parse_args()
    model_path = Path(args.model)
    out_path = Path(args.out) if args.out else model_path.with_suffix(".triggers.yaml")
    sys.exit(gen_triggers(model_path, out_path, args.dry_run))
