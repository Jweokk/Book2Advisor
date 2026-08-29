#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选融合（extract_candidates.py 的产物 → Method Model yaml）。

两阶段：
    1. LLM 分组决策：把全部候选（紧凑化）交给 LLM，按三重验证门槛
       （V1 跨域 / V2 预测力 / V3 独特性）分组：合并同义、降级、淘汰。
    2. 程序化组装：按决策表生成 yaml —— 同组候选合并为多 evidence
       （跨源数 ≥3 → E5，≥2 → E4，单篇 → E3），淘汰项写入 rejected/。

用法:
    python3 scripts/merge_candidates.py \\
        --src /tmp/<person>-extract \\
        --person <id> --name <中文名> --domain <领域> --brief <简介> \\
        --out data/methods/<person>/<model>-v0.1.yaml

产物必须通过 scripts/validate_schema.py（脚本末尾自动校验，exit 0 才算成功）。
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from core.runtime.llm import DeepSeekClient, extract_json, LLMError

CROSS_BATCH_SYSTEM = """你是方法论融合器（跨批合并）。以下是分批分组的结果（每批已按三重验证门槛分组），
请做**跨批最终合并**：
- 不同批中同义/近义的 group（同 type，名字或陈述指向同一方法论）→ 合并为一个 group，candidate_ids 取并集
- 其余 group 原样保留（type/name/statement/ids 不变）
- 仍按 V1/V2/V3 门槛：明显常识废话的 group 可改 type 为 rejected
只输出 JSON：{"groups": [同单批格式]}。"""

SYSTEM = """你是方法论融合器。把候选清单融合为「人物方法模型」的骨架。

三重验证门槛（宁缺毋滥）：
- V1 跨域：该框架出现在 ≥2 个独立语境/语料？只出现一次 → 降级（原则→规则/证据）
- V2 预测力：能推断语料里没明说的新问题？只能复述例子 → 降级为规则
- V3 独特性：抹掉人名，普通聪明人说得出来吗？常识废话（"要努力"）→ 淘汰
通过 3 项 → principle；通过 1-2 项 → rule；案例候选 → case；诊断步骤 → diagnostic；0 项 → rejected。

合并规则：跨篇同义表达（如"聚焦"="压强"="城墙口"）合并为**一个**实体，保留所有候选为 evidence。

只输出 JSON（不要其他内容）：
{
  "groups": [
    {"type": "principle|rule|case|diagnostic|rejected",
     "name": "中文短名（实体名）",
     "statement": "一句话概括（principle/rule 必填）",
     "candidate_ids": ["<候选id>", "..."],
     "reason": "合并/降级/淘汰原因（一句话）"}
  ]
case 类型的 group 额外必填：context/problem/decision/action/outcome/reasoning/principle
（principle 填该案例归属的原则中文名，须与某个 principle group 的 name 一致；拿不准就填最接近的）
}
要求：每个候选必须恰好进入一个 group；type=rejected 的 group 也要列出候选与原因。"""


def load_candidates(src_dir: Path) -> list[dict]:
    """读取全部候选 JSON，紧凑化为候选列表（含全局 id）。"""
    cands: list[dict] = []
    for jp in sorted(src_dir.glob("*.json")):
        fid = jp.stem
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  ⚠️ {fid}.json 解析失败，跳过：{e}", flush=True)
            continue
        counters: dict[str, int] = {}
        def _cid(t: str) -> str:
            counters[t] = counters.get(t, 0) + 1
            return f"{fid}-{t[:4]}-{counters[t]}"
        for item in data.get("principles", []):
            cands.append({"id": _cid("principle"), "fid": fid, "type": "principle",
                          "name": item.get("name", ""), "statement": item.get("statement", ""),
                          "quote": item.get("quote", ""), "raw": item})
        for item in data.get("rules", []):
            cands.append({"id": _cid("rule"), "fid": fid, "type": "rule",
                          "name": item.get("name", ""), "statement": item.get("condition", "") + " → " + item.get("decision", ""),
                          "quote": item.get("quote", ""), "raw": item})
        for item in data.get("cases", []):
            cands.append({"id": _cid("case"), "fid": fid, "type": "case",
                          "name": item.get("name", ""), "statement": item.get("context", "")[:80],
                          "quote": item.get("quote", ""), "raw": item})
        for item in data.get("diagnostics", []):
            cands.append({"id": _cid("diagnostic"), "fid": fid, "type": "diagnostic",
                          "name": item.get("name", ""), "statement": "→".join(item.get("order", [])),
                          "quote": "", "raw": item})
        for item in data.get("anti_patterns", []):
            # 反模式 → 并入规则候选（r-不做X），保留 quote
            cands.append({"id": _cid("antipat"), "fid": fid, "type": "anti_pattern",
                          "name": "不做" + item.get("name", ""), "statement": item.get("description", ""),
                          "quote": item.get("quote", ""), "raw": item})
    return cands


def compact_payload(cands: list[dict]) -> str:
    """紧凑化候选清单（只留判定所需字段，控制输入体积）。"""
    lines = []
    for c in cands:
        q = c["quote"].replace("\n", " ")[:60]
        lines.append(f"[{c['id']}|{c['type']}|{c['name']}] {c['statement'][:60]} 引:'{q}'")
    return "\n".join(lines)


def llm_group(cands: list[dict], client: DeepSeekClient) -> list[dict]:
    """LLM 分组决策（带重试）。"""
    payload = compact_payload(cands)
    user = f"共 {len(cands)} 条候选，请融合分组：\n\n{payload}"
    last_err = ""
    for attempt in range(3):
        try:
            resp = client.chat(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                temperature=0.2, max_tokens=12000,
            )
            data = extract_json(resp)
            groups = data.get("groups", [])
            if not groups:
                raise LLMError("分组结果为空")
            return groups
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(3 * (attempt + 1))
    raise LLMError(f"LLM 分组失败（3 次重试后）：{last_err}")


def evidence_level(n_sources: int) -> str:
    """跨源数 → 证据等级（E1 未采用；E2 弱；E3 单源；E4 双源；E5 三源+）。"""
    if n_sources >= 3:
        return "E5"
    if n_sources == 2:
        return "E4"
    return "E3"


def _compact_groups(groups: list[dict]) -> list[dict]:
    """group 紧凑化（只留判定所需字段，去 statement 减体积防超限）。"""
    return [{"type": g.get("type", "rejected"), "name": g.get("name", "") or "",
             "candidate_ids": g.get("candidate_ids", []) or []} for g in groups]


def _cross_merge(batches: list[list[dict]], client: DeepSeekClient) -> list[dict]:
    """多批 groups 跨批合并（4 路扇出：输入 ~50-60 组，稳定且调用次数少）。"""
    merged = [g for b in batches for g in b]
    compact = _compact_groups(merged)
    payload = json.dumps({"batches": compact}, ensure_ascii=False)
    last_err = ""
    for attempt in range(3):
        try:
            resp = client.chat(
                [{"role": "system", "content": CROSS_BATCH_SYSTEM},
                 {"role": "user", "content": f"共 {len(compact)} 组，跨批合并：\n{payload}"}],
                temperature=0.2, max_tokens=16000,
            )
            data = extract_json(resp)
            groups = data.get("groups", [])
            if not groups:
                raise LLMError("跨批合并结果为空")
            return groups
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(3 * (attempt + 1))
    raise LLMError(f"跨批合并失败（3 次重试后）：{last_err}")


def llm_group_batched(cands: list[dict], client: DeepSeekClient, batch_size: int = 30) -> list[dict]:
    """大候选集分批分组 + 层级跨批合并（每层两两合并，输入永远可控）。"""
    if len(cands) <= batch_size:
        return llm_group(cands, client)
    batches = [cands[i:i + batch_size] for i in range(0, len(cands), batch_size)]
    group_batches: list[list[dict]] = []
    for i, batch in enumerate(batches, 1):
        print(f"  批 {i}/{len(batches)}（{len(batch)} 条）→ 分组…", flush=True)
        group_batches.append(llm_group(batch, client))
    # 层级合并（4 路扇出）：B 批 → ceil(B/4) → … → 1（13 批仅需 5 次跨批调用）
    round_no = 0
    while len(group_batches) > 1:
        round_no += 1
        nxt: list[list[dict]] = []
        for i in range(0, len(group_batches), 4):
            chunk = group_batches[i:i + 4]
            if len(chunk) == 1:
                nxt.append(chunk[0])
                continue
            # 组数自适应：单次合并 ≤40 组（防输出 JSON 超 max_tokens 截断）
            while sum(len(b) for b in chunk) > 40 and len(chunk) > 1:
                chunk = chunk[:len(chunk) // 2]
            n = sum(len(b) for b in chunk)
            print(f"  合并轮 {round_no}：{len(chunk)} 批共 {n} 组 → 合并…", flush=True)
            nxt.append(_cross_merge(chunk, client))
        group_batches = nxt
    return group_batches[0]


def assemble(groups: list[dict], cands: list[dict], src_dir: Path,
             person: dict, out_path: Path, rejected_dir: Path) -> tuple[dict, list[dict]]:
    """按决策表程序化组装 Method Model。"""
    by_id = {c["id"]: c for c in cands}
    used = set()
    model: dict = {
        "method_version": "v0.1",
        "person": person,
        "sources": [],
        "principles": [], "rules": [], "cases": [], "diagnostics": [],
        "tensions": [], "evolution": [],
    }
    rejected: list[dict] = []

    # sources：从实际用到的候选 fid 生成（保持输入顺序）
    used_fids: list[str] = []
    for g in groups:
        for cid in g.get("candidate_ids", []):
            c = by_id.get(cid)
            if c and c["fid"] not in used_fids:
                used_fids.append(c["fid"])
    for fid in used_fids:
        model["sources"].append({"id": fid, "title": fid, "type": "speech", "file": fid, "date": "unknown"})

    # 各类型实体
    for g in groups:
        gtype = g.get("type", "rejected")
        ids = g.get("candidate_ids", [])
        members = [by_id[cid] for cid in ids if cid in by_id]
        if not members:
            continue
        used.update(ids)
        gname = g.get("name", "").strip()
        if gtype == "rejected" or not gname:
            for m in members:
                rejected.append({"candidate": m["id"],
                                 "reason": g.get("reason") or "LLM 分组判定淘汰（未给原因）",
                                 "name": m["name"], "statement": m["statement"][:100]})
            continue
        # evidence：同组候选跨篇合并
        evid = []
        seen_src: dict[str, int] = {}
        for m in members:
            if m["quote"]:
                seen_src[m["fid"]] = seen_src.get(m["fid"], 0) + 1
        for m in members:
            if m["quote"]:
                evid.append({
                    "source": m["fid"],
                    "loc": m["id"],
                    "quote": m["quote"][:60],
                    "level": evidence_level(len(seen_src)),
                })
        if gtype == "principle":
            n_src = len({e["source"] for e in evid})
            model["principles"].append({
                "id": gname, "name": gname, "statement": g.get("statement", gname),
                "confidence": "high" if n_src >= 2 else "medium",
                "evidence": evid,
            })
        elif gtype == "rule":
            m0 = members[0]["raw"]
            cond = m0.get("condition", g.get("statement", gname))
            dec = m0.get("decision", "")
            if not dec and "→" in g.get("statement", ""):
                dec = g["statement"].split("→")[-1].strip()
            model["rules"].append({
                "id": "r-" + gname, "name": gname,
                "trigger": [cond],
                "diagnose": [cond],
                "decisions": {cond: dec} if dec else {"default": g.get("statement", gname)},
                "exceptions": [],
                "evidence": evid,
            })
        elif gtype == "case":
            if not g.get("principle"):
                # 没有原则归属的案例 → 宁缺毋滥，转淘汰并提示
                rejected.append({"candidate": "|".join(ids), "reason": "case 缺少 principle 归属（LLM 未填，脚本兜底）",
                                 "name": gname, "statement": g.get("statement", "")[:100]})
                continue
            m0 = members[0]["raw"]
            model["cases"].append({
                "id": "c-" + gname, "name": gname,
                "context": g.get("context") or m0.get("context", ""),
                "problem": g.get("problem") or m0.get("problem", "") or g.get("statement", ""),
                "decision": g.get("decision") or m0.get("decision", ""),
                "action": g.get("action") or m0.get("action", "") or g.get("decision") or m0.get("decision", ""),
                "outcome": g.get("outcome") or m0.get("outcome", ""),
                "reasoning": g.get("reasoning") or m0.get("reasoning", "") or g.get("statement", ""),
                "principle": [g["principle"]] if isinstance(g["principle"], str) else g["principle"],
                "evidence": evid,
            })
        elif gtype == "diagnostic":
            orders = [m["raw"].get("order", []) for m in members if m["raw"].get("order")]
            model["diagnostics"].append({
                "id": "d-" + gname, "name": gname,
                "order": orders[0] if orders else [],
            })

    # 未分组的候选（LLM 遗漏）→ 视为淘汰并提示
    orphan = [c for c in cands if c["id"] not in used]
    for c in orphan:
        rejected.append({"candidate": c["id"], "reason": "LLM 分组遗漏（脚本兜底淘汰）",
                         "name": c["name"], "statement": c["statement"][:100]})

    # 写 yaml
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_dump_yaml(model), encoding="utf-8")
    # 淘汰记录
    if rejected:
        rejected_dir.mkdir(parents=True, exist_ok=True)
        (rejected_dir / "rejected.json").write_text(
            json.dumps(rejected, ensure_ascii=False, indent=1), encoding="utf-8")
    return model, rejected


def _dump_yaml(model: dict) -> str:
    """手工 yaml 序列化（避免 pyyaml 对中文引号的特殊转义，产出可读）。"""
    lines = [f"method_version: {model['method_version']}", "person:", "  id: " + model["person"]["id"],
             "  name: " + model["person"]["name"], "  domain: " + model["person"]["domain"],
             "  brief: " + model["person"]["brief"], "sources:"]
    for s in model["sources"]:
        lines.append(f"  - id: {s['id']}")
        lines.append(f"    title: {s['title']}")
        lines.append(f"    type: {s['type']}")
        lines.append(f"    file: {s['file']}")
        lines.append(f"    date: {s['date']}")
    for key, prefix in [("principles", ""), ("rules", "r-"), ("cases", "c-"), ("diagnostics", "d-")]:
        if not model[key]:
            lines.append(f"{key}: []")
            continue
        lines.append(f"{key}:")
        for ent in model[key]:
            ent_id = ent["id"] if ent["id"].startswith(prefix) else prefix + ent["id"]
            lines.append(f"  - id: {ent_id}")
            lines.append(f"    name: {ent['name']}")
            for k in ("statement", "confidence", "context", "problem", "decision", "action",
                      "outcome", "reasoning", "order", "file"):
                if k in ent and ent[k]:
                    if k == "order":
                        lines.append("    order:")
                        for step in ent[k]:
                            lines.append(f"      - {step}")
                    else:
                        lines.append(f"    {k}: {ent[k]}")
            if "trigger" in ent:
                lines.append("    trigger:")
                for t in ent["trigger"]:
                    lines.append(f"      - {t}")
            if "diagnose" in ent:
                lines.append("    diagnose:")
                for t in ent["diagnose"]:
                    lines.append(f"      - {t}")
            if "decisions" in ent:
                lines.append("    decisions:")
                for kk, vv in ent["decisions"].items():
                    lines.append(f"      {kk}: {vv}")
            if "exceptions" in ent:
                lines.append("    exceptions: []")
            if ent.get("principle"):
                lines.append("    principle: [" + ", ".join(ent["principle"]) + "]")
            if ent.get("evidence"):
                lines.append("    evidence:")
                for e in ent["evidence"]:
                    lines.append(f"      - source: {e['source']}")
                    lines.append(f"        loc: {e['loc']}")
                    lines.append(f"        quote: {e['quote']}")
                    lines.append(f"        level: {e['level']}")
    for key in ("tensions", "evolution"):
        lines.append(f"{key}: []")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="候选目录（extract_candidates.py 输出）")
    ap.add_argument("--person", required=True, help="人物 id（如 cao-dewang）")
    ap.add_argument("--name", required=True, help="人物中文名（如 曹德旺）")
    ap.add_argument("--domain", default="企业管理", help="领域（如 企业管理 / 制造业）")
    ap.add_argument("--brief", default="", help="人物一句话简介")
    ap.add_argument("--out", required=True, help="输出 yaml 路径")
    args = ap.parse_args()

    src_dir = Path(args.src)
    if not src_dir.is_dir():
        sys.exit(f"错误：候选目录不存在：{src_dir}")
    cands = load_candidates(src_dir)
    if not cands:
        sys.exit("错误：没有读到任何候选（检查 --src 下是否有 extract_candidates.py 的产物 JSON）")
    print(f"候选 {len(cands)} 条（{len({c['fid'] for c in cands})} 篇）→ LLM 分组…", flush=True)

    client = DeepSeekClient()
    groups = llm_group_batched(cands, client)
    print(f"分组完成：{len(groups)} 组（principle {sum(1 for g in groups if g['type']=='principle')} / "
          f"rule {sum(1 for g in groups if g['type']=='rule')} / case {sum(1 for g in groups if g['type']=='case')} / "
          f"diagnostic {sum(1 for g in groups if g['type']=='diagnostic')} / rejected {sum(1 for g in groups if g['type']=='rejected')}）", flush=True)

    out_path = Path(args.out)
    rejected_dir = out_path.parent / "rejected"
    model, rejected = assemble(groups, cands, src_dir,
                               {"id": args.person, "name": args.name, "domain": args.domain, "brief": args.brief},
                               out_path, rejected_dir)
    print(f"组装完成：{len(model['principles'])} 原则 / {len(model['rules'])} 规则 / "
          f"{len(model['cases'])} 案例 / {len(model['diagnostics'])} 诊断 / 淘汰 {len(rejected)}", flush=True)
    if not model["cases"]:
        print("⚠️ 无案例通过分组——schema 要求 ≥1 案例：请人工补充（可调整分组或手动添加）", flush=True)
    if not model["principles"]:
        print("⚠️ 无原则通过分组——请检查候选质量或放宽分组门槛", flush=True)

    # 自动校验
    import subprocess
    r = subprocess.run([sys.executable, str(PROJECT_ROOT / "scripts" / "validate_schema.py"), str(out_path)],
                       capture_output=True, text=True)
    print(r.stdout.strip()[-500:])
    if r.returncode != 0:
        sys.exit(f"❌ validate_schema 未通过（exit {r.returncode}），见上方错误。修复后重跑 --out 可覆盖。")
    print(f"✅ 融合完成并通过校验：{out_path}")


if __name__ == "__main__":
    main()
