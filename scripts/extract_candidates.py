#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语料逐篇提取（后台跑，每篇独立可断点续跑）。

把 data/sources/<person>/<type>/*.md 逐篇交给 LLM，提取方法论候选
（principles / rules / cases / anti_patterns / diagnostics），输出 JSON 供后续融合。

用法:
    python3 scripts/extract_candidates.py --src data/sources/<person>/book --out /tmp/<person>-extract
    # --src 目录下每篇 .md 一篇一个 JSON（产物存在则跳过，断点续跑）

融合（候选 JSON → Method Model yaml）见 docs/COMPILING.md。
"""
import argparse
import sys
import json
import time
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from core.runtime.llm import DeepSeekClient

MAX_WORKERS = 3

SYSTEM = """你是方法论提取器。从给定的目标人物讲话/文章/采访/书中，提取方法论候选。只输出 JSON（不要其他内容）：
{
  "principles": [{"name": "中文短名", "statement": "一句话概括该原则", "quote": "原文短句≤60字", "source_note": "篇目内定位"}],
  "rules": [{"name": "中文短名", "condition": "什么情况下", "decision": "怎么做", "quote": "原文短句≤60字"}],
  "cases": [{"name": "中文短名", "context": "背景", "decision": "决策", "outcome": "结果", "quote": "原文短句≤60字"}],
  "anti_patterns": [{"name": "中文短名", "description": "他反对的做法", "quote": "原文短句≤60字"}],
  "diagnostics": [{"name": "中文短名", "order": ["步骤1", "步骤2"]}]
}
要求：quote 必须逐字来自原文（≤60字，去掉引号标点差异）；宁缺毋滥，只收方法论密度高的；若某类无内容则给空数组。"""


def extract_one(client, src_dir: Path, path: Path, out_dir: Path) -> str:
    fid = path.stem
    jp = out_dir / f"{fid}.json"
    if jp.exists():  # 断点续跑
        return f"{fid} 跳过(已有)"
    text = path.read_text(encoding="utf-8", errors="ignore")
    # 去掉 frontmatter
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    # 截断控制：单篇最多 18K 字符（deepseek 系推理模型对超长单次输入易返回空响应，
    # 内部实测 ≤18K 分段提取稳定；超长语料建议先拆分为多篇 .md 再提取）
    text = text[:18000]
    user = f"【语料标题】{fid}\n【语料正文】\n{text}"
    last_err = ""
    for attempt in range(3):
        try:
            resp = client.chat(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                temperature=0.2, max_tokens=12000,
            )
            # 容错 JSON：去 ```json 围栏、截取 { } 区间
            resp = resp.strip()
            if resp.startswith("```"):
                resp = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp)
            data = json.loads(resp)
            jp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            return f"{fid} ✓ ({len(data.get('principles', []))}P/{len(data.get('rules', []))}R/{len(data.get('cases', []))}C)"
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:60]}"
            time.sleep(3 * (attempt + 1))
    return f"{fid} FAIL {last_err}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="语料目录（data/sources/<person>/<type>）")
    ap.add_argument("--out", required=True, help="输出目录（每篇一个 JSON）")
    args = ap.parse_args()

    src_dir = Path(args.src)
    out_dir = Path(args.out)
    if not src_dir.is_dir():
        sys.exit(f"错误：语料目录不存在：{src_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(src_dir.glob("*.md"))
    if not files:
        sys.exit(f"错误：目录下没有 .md 语料：{src_dir}")
    print(f"语料 {len(files)} 篇 → {out_dir} | 并发 {MAX_WORKERS}", flush=True)

    client = DeepSeekClient()
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(extract_one, client, src_dir, f, out_dir): f for f in files}
        for fut in as_completed(futures):
            done += 1
            print(f"  {done}/{len(files)} {fut.result()}", flush=True)
    print(f"\n完成：{out_dir}（{done} 篇）", flush=True)


if __name__ == "__main__":
    main()
