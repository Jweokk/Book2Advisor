#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评估批处理：并发调用 run_chain，输出 md 测试报告。

用法:
    python3 scripts/batch_ask.py --person <person_dir> --model <model.yaml> --group core
    # person_dir 为 evaluations/ 下的目录名（如 example）；--model 指向方法模型 yaml

题目来源：evaluations/<person_dir>/questions/<group>.md（core 组对应 40-core.md）。
输出：evaluations/<person_dir>/batch-<group>-answers.md（core 组为 batch-40-answers.md）。
"""
import sys
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import yaml
from core.runtime.ask import run_chain
from core.runtime.llm import DeepSeekClient

MAX_WORKERS = 4

# 组 → 题目文件名（core 组对应 40-core.md，其余组同名）
GROUP_FILE = {
    "core": "40-core.md",
    "lures": "lures.md",
    "confusions": "confusions.md",
    "out-of-scope": "out-of-scope.md",
}
# 组 → 中文说明（报告头用）
GROUP_LABEL = {
    "core": "核心题（40 题）",
    "lures": "诱饵题（lures）",
    "confusions": "混淆题（confusions）",
    "out-of-scope": "超范围题（out-of-scope）",
}


def load_questions(path):
    """从题目文件解析问题列表。

    规则：逐行读取；空行跳过；'#' 开头的注释行跳过（设计理由/陪跑原则说明）；
    匹配 ^\\d+[.、]\\s*(.*) 提取问题文本（去掉题号前缀）；不匹配行跳过。
    """
    if not path.is_file():
        sys.exit(f"错误：题目文件不存在：{path}")
    questions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^\d+[.、]\s*(.*)", line)
        if m and m.group(1).strip():
            questions.append(m.group(1).strip())
    return questions


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True, help="evaluations/ 下的目录名（如 example）")
    ap.add_argument("--model", required=True, help="方法模型 yaml 路径（绝对或相对）")
    ap.add_argument("--group", default="core", choices=["core", "lures", "confusions", "out-of-scope"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    ev_dir = PROJECT_ROOT / "evaluations" / args.person
    if not ev_dir.is_dir():
        sys.exit(f"错误：评估目录不存在：{ev_dir}（先建 evaluations/<person>/questions/）")
    questions_path = ev_dir / "questions" / GROUP_FILE[args.group]
    # 输出路径：core 组保持 batch-40-answers.md，其余组 batch-<group>-answers.md；--out 可覆盖
    out_name = "batch-40-answers.md" if args.group == "core" else f"batch-{args.group}-answers.md"
    out_path = ev_dir / out_name
    if args.out:
        out_path = Path(args.out)

    model_path = Path(args.model)
    if not model_path.is_file():
        sys.exit(f"错误：方法模型文件不存在：{model_path}")
    questions = load_questions(questions_path)
    model = yaml.safe_load(model_path.open(encoding="utf-8"))
    person_name = model.get("person", {}).get("name", args.person)
    sources = "；".join(s.get("title", s.get("id", "")) for s in model.get("person", {}).get("sources", [])) or "Method Model"

    def run_one(idx, q):
        t0 = time.time()
        try:
            result = run_chain(model, q)
            return idx, q, result["trace"], time.time() - t0, None
        except Exception as e:
            return idx, q, "", time.time() - t0, f"{type(e).__name__}: {e}"

    print(f"模型: {person_name} | 组别: {args.group} | 问题数: {len(questions)} | 并发: {MAX_WORKERS}", flush=True)
    results = [None] * len(questions)
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(run_one, i, q): i for i, q in enumerate(questions)}
        for fut in as_completed(futures):
            idx, q, trace, dt, err = fut.result()
            results[idx] = (q, trace, dt, err)
            done += 1
            status = f"[{dt:.0f}s]" if not err else f"[FAIL {err[:60]}]"
            print(f"  {done}/{len(questions)} 题{idx+1}{status}", flush=True)

    out = [f"# {person_name} {GROUP_LABEL[args.group]}测试报告\n",
           f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M')} | 组别：{args.group} | 题数：{len(questions)} | 数据源：{sources}\n"]
    fail_count = 0
    for i, (q, trace, dt, err) in enumerate(results, 1):
        out.append(f"\n---\n\n## 问题 {i}：{q}\n")
        if err:
            out.append(f"\n> ❌ 失败：{err}\n")
            fail_count += 1
        else:
            out.append(trace)
    out.append(f"\n---\n\n**统计：成功 {len(questions)-fail_count}/{len(questions)}，失败 {fail_count}**\n")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out), encoding="utf-8")
    print(f"\n完成：{out_path}（成功 {len(questions)-fail_count}/{len(questions)}，失败 {fail_count}）", flush=True)


if __name__ == "__main__":
    main()
