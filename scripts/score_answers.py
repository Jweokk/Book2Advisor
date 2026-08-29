#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评估集评分：按 rubric 给答案逐题打分（0-2 × 判分点）。

用法:
    python3 scripts/score_answers.py --person <person_dir> --group <group> [--judge-model <模型>]
    # person_dir 为 evaluations/ 下的目录名（与 batch_ask.py --person 一致）

core 组：v0.1 / v0.4 双版本对比（若存在 batch-40-answers-v0.1.md）；
lures/confusions/out-of-scope 组：单版本评分。
评分使用独立 judge 模型（--judge-model，默认 deepseek-v4-flash），与答题模型分离——
答题 agent 与评分 agent 双 agent 盲测（LLM 自评 skill 质量准确率仅约 46%）。
"""
import sys
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from core.runtime.llm import DeepSeekClient

MAX_WORKERS = 4

# 组 → rubric 文件名（core 组兼容 eval-rubric-40.md）
GROUP_RUBRIC = {
    "core": "eval-rubric-40.md",
    "lures": "eval-rubric-lures.md",
    "confusions": "eval-rubric-confusions.md",
    "out-of-scope": "eval-rubric-out-of-scope.md",
}
# 组 → 答案文件名
GROUP_ANSWER = {
    "core": "batch-40-answers.md",
    "lures": "batch-lures-answers.md",
    "confusions": "batch-confusions-answers.md",
    "out-of-scope": "batch-out-of-scope-answers.md",
}

SYSTEM = """你是评估打分员。严格按给定的评分要点（每项 0-2 分：0=完全缺失/错误，1=部分符合，2=符合预期）给答案打分。只输出 JSON：{"scores": [整数列表,顺序与判分点一致], "total": 总分, "reason": "50字以内理由"}。不要加其他内容。"""


def parse_rubric(text):
    """解析 rubric 为 {题号: {points: [...], type: 字母, question: str}}"""
    items = {}
    # 按 "## 题 N：" 分段
    segs = re.split(r"^## 题 (\d+)：", text, flags=re.M)
    for i in range(1, len(segs), 2):
        n = int(segs[i])
        body = segs[i + 1]
        # 类型：core 组 A-E；lures 组 L；confusions 组 C；out-of-scope 组 O
        qm = re.search(r"- 类型：([A-ELO])", body)
        qtext = re.search(r"^## 题 \d+：(.*)$", body, re.M)
        # 评分要点：以 "- " 开头且含（0-2）的行
        points = re.findall(r"^  - (.+?)（0-2）", body, re.M)
        if not points:
            points = re.findall(r"^  - (.+?)(?:（0-2）|\(0-2\))", body, re.M)
        items[n] = {"type": qm.group(1) if qm else "?", "points": points,
                    "question": (qtext.group(1).strip() if qtext else "")}
    return items


def parse_answers(text):
    """解析答案文件为 {题号: trace}"""
    ans = {}
    segs = re.split(r"^## 问题 (\d+)：", text, flags=re.M)
    for i in range(1, len(segs), 2):
        n = int(segs[i])
        ans[n] = segs[i + 1].strip()
    return ans


def parse_json_reply(resp):
    """容错 JSON 解析：去代码块围栏、截取 { } 区间"""
    import json
    if not resp or not resp.strip():
        raise ValueError("空响应")
    resp = resp.strip()
    if resp.startswith("```"):
        resp = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp)
    try:
        return json.loads(resp)
    except Exception:
        m = re.search(r"\{.*\}", resp, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def score_one(client, n, q, points, answer, version):
    if not answer:
        return n, version, None, "无答案"
    user = f"【题目】{q}\n\n【评分要点】\n" + "\n".join(f"{i+1}. {p}（0-2分）" for i, p in enumerate(points)) + \
           f"\n\n【待评分答案（{version}）】\n{answer[:6000]}"
    t0 = time.time()
    last_err = ""
    for attempt in range(3):
        try:
            resp = client.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                               temperature=0.1, max_tokens=800)
            data = parse_json_reply(resp)
            scores = data.get("scores", [])
            total = data.get("total", sum(scores))
            return n, version, {"scores": scores, "total": total, "reason": data.get("reason", "")}, f"[{time.time()-t0:.0f}s]"
        except Exception as e:
            last_err = str(e)[:60]
            time.sleep(2 * (attempt + 1))
    return n, version, None, f"FAIL {last_err}"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True, help="evaluations/ 下的目录名（如 example，与 batch_ask.py --person 一致）")
    ap.add_argument("--group", default="core", choices=["core", "lures", "confusions", "out-of-scope"])
    ap.add_argument("--judge-model", default="deepseek-v4-flash", help="评分（judge）模型名，独立于答题模型")
    ap.add_argument("--base", default=str(PROJECT_ROOT / "evaluations"), help="评估数据根目录")
    args = ap.parse_args()

    base = Path(args.base) / args.person
    if not base.is_dir():
        sys.exit(f"错误：评估目录不存在：{base}")
    single = args.group != "core"  # 非 core 组：单版本评分模式

    rubric_path = base / GROUP_RUBRIC[args.group]
    if not rubric_path.is_file():
        sys.exit(f"错误：rubric 文件不存在：{rubric_path}（请先创建该组的评分标准）")
    rubric = parse_rubric(rubric_path.read_text(encoding="utf-8"))

    v4_path = base / GROUP_ANSWER[args.group]
    if not v4_path.is_file():
        sys.exit(f"错误：答案文件不存在：{v4_path}（请先运行 scripts/batch_ask.py --group {args.group}）")
    v4 = parse_answers(v4_path.read_text(encoding="utf-8"))

    v1 = {}
    if not single:
        # core 组：v0.1 / v0.4 双版本对比（v0.1 文件可选）
        v1_path = base / "batch-40-answers-v0.1.md"
        if v1_path.is_file():
            v1 = parse_answers(v1_path.read_text(encoding="utf-8"))

    client = DeepSeekClient(model=args.judge_model)
    if single:
        print(f"rubric 题数: {len(rubric)} | 答案: {len(v4)} | 组别: {args.group} | 评分模型: {args.judge_model}", flush=True)
    else:
        print(f"rubric 题数: {len(rubric)} | v0.1 答案: {len(v1)} | v0.4 答案: {len(v4)} | 组别: {args.group} | 评分模型: {args.judge_model}", flush=True)

    results = {n: {} for n in rubric}
    # 任务列表：非 core 组只提交 v0.4；core 组双版本（相同答案去重复用，不重复提交）
    job_list = []
    for n in rubric:
        for ver, ans in (("v0.1", v1.get(n, "")), ("v0.4", v4.get(n, ""))):
            if single and ver == "v0.1":
                continue
            if ver == "v0.4" and not single and ans == v1.get(n, ""):
                continue
            job_list.append((n, ver, ans))
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(score_one, client, n, rubric[n]["question"], rubric[n]["points"], ans, ver): (n, ver)
                for (n, ver, ans) in job_list}
        for fut in as_completed(futs):
            n, ver, res, note = fut.result()
            results[n][ver] = res
            if ver == "v0.1" and "v0.4" not in results[n]:
                results[n]["v0.4"] = res
            done += 1
            print(f"  {done}/{len(job_list)} 题{n}({ver}){note}", flush=True)

    # 生成报告
    if single:
        lines = [f"# Method Advisor 评估报告：{args.group} 组（{len(rubric)} 题）\n",
                 f"> 生成：{time.strftime('%Y-%m-%d %H:%M')} | 组别：{args.group} | 评分模型：{args.judge_model} | 评分标准：{GROUP_RUBRIC[args.group]}（每题判分点 × 0-2 分）\n"]
    else:
        lines = [f"# Method Advisor 评估报告：v0.1 vs v0.4（{args.group} 组 {len(rubric)} 题）\n",
                 f"> 生成：{time.strftime('%Y-%m-%d %H:%M')} | 组别：{args.group} | 评分模型：{args.judge_model} | 评分标准：{GROUP_RUBRIC[args.group]}（每题判分点 × 0-2 分）\n"]
    lines.append("## 汇总\n")
    if single:
        lines.append("| 总分 | 平均/题 | 满分题数 |")
        lines.append("|---|---|---|")
        totals = [results[n]["v0.4"]["total"] for n in results if results[n].get("v0.4")]
        max_per = len(rubric[next(iter(rubric))]["points"]) * 2  # 单版本组满分 = 判分点数 × 2
        full = sum(1 for t in totals if t >= max_per)
        lines.append(f"| {sum(totals)} | {sum(totals)/len(totals):.1f} | {full} |")
    else:
        lines.append("| 版本 | 总分 | 平均/题 | 满分题数 |")
        lines.append("|---|---|---|---|")
        for ver in ("v0.1", "v0.4"):
            totals = [results[n][ver]["total"] for n in results if results[n].get(ver)]
            full = sum(1 for t in totals if t >= len(rubric[next(iter(rubric))]["points"]) * 2)
            lines.append(f"| {ver} | {sum(totals)} | {sum(totals)/len(totals):.1f} | {full} |")
    lines.append("")
    # 分类对比（A-E）：仅 core 组双版本执行；非 core 组类型为 L/C/O，跳过该小节
    if not single:
        lines.append("## 按类型对比（平均分）\n")
        lines.append("| 类型 | v0.1 | v0.4 | 差值 |")
        lines.append("|---|---|---|---|")
        for t in "ABCDE":
            ns = [n for n, d in rubric.items() if d["type"] == t]
            if not ns:
                continue
            a = sum(results[n]["v0.1"]["total"] for n in ns if results[n].get("v0.1")) / len(ns)
            b = sum(results[n]["v0.4"]["total"] for n in ns if results[n].get("v0.4")) / len(ns)
            lines.append(f"| {t} | {a:.1f} | {b:.1f} | {b-a:+.1f} |")
        lines.append("")
    # 逐题明细
    lines.append("## 逐题明细\n")
    if single:
        lines.append("| 题 | 类型 | 得分 | 理由 |")
        lines.append("|---|---|---|---|")
        for n in sorted(rubric):
            r4 = results[n].get("v0.4") or {}
            t4 = r4.get("total", "-") if r4 else "-"
            reason = (r4.get("reason") or "")[:40] if r4 else ""
            lines.append(f"| {n} | {rubric[n]['type']} | {t4} | {reason} |")
    else:
        lines.append("| 题 | 类型 | v0.1 | v0.4 | 差值 | 提升最大判分点(v0.4理由) |")
        lines.append("|---|---|---|---|---|---|")
        for n in sorted(rubric):
            r1 = results[n].get("v0.1") or {}
            r4 = results[n].get("v0.4") or {}
            t1 = r1.get("total", "-") if r1 else "-"
            t4 = r4.get("total", "-") if r4 else "-"
            diff = (r4.get("total", 0) - r1.get("total", 0)) if r1 and r4 else "-"
            reason = (r4.get("reason") or "")[:40] if r4 else ""
            lines.append(f"| {n} | {rubric[n]['type']} | {t1} | {t4} | {diff} | {reason} |")
    lines.append("")
    # 失败项
    if single:
        fails = [n for n in results if not results[n].get("v0.4")]
    else:
        fails = [n for n in results if not results[n].get("v0.4") or not results[n].get("v0.1")]
    if fails:
        lines.append(f"## 未评分题（答案缺失/失败）：{fails}\n")
    # 输出：core 组保持 score-report.md，非 core 组按组区分
    OUT = base / ("score-report.md" if not single else f"score-report-{args.group}.md")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n完成：{OUT}")


if __name__ == "__main__":
    main()
