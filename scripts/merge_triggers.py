#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_triggers.py — 把 gen_triggers.py 生成的 trigger 合并进 Method Model 主文件。

用法: python3 scripts/merge_triggers.py --model <yaml路径> --triggers <triggers.yaml> [--backup]

按「块」处理：每个 "- id: xxx" 开始到下一个 "- id:" 之前为一个 principle 块，
在块内 "  confidence:" 行之后插入 trigger 块。不丢行、不重排、保留注释。
"""
import argparse
import shutil
import sys
from pathlib import Path

import yaml


def merge(model_path: Path, triggers_path: Path, backup: bool = False) -> int:
    with triggers_path.open(encoding="utf-8") as fh:
        triggers = yaml.safe_load(fh)
    if not isinstance(triggers, dict):
        print(f"错误：{triggers_path} 不是 dict，实际 {type(triggers).__name__}")
        return 1

    lines = model_path.read_text(encoding="utf-8").split("\n")
    out: list[str] = []
    inserted = set()
    merged_count = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.startswith("- id: "):
            out.append(line)
            i += 1
            continue
        pid = line.split("- id: ", 1)[1].strip()
        # 收集本块全部行（直到下一个 "- id: " 或文件尾）
        j = i + 1
        block = [line]
        while j < n and not lines[j].startswith("- id: "):
            block.append(lines[j])
            j += 1
        # 在块内找 confidence 行
        conf_idx = None
        for bi, bl in enumerate(block):
            if bl.startswith("  confidence:"):
                conf_idx = bi
                break
        if pid in triggers and pid not in inserted and conf_idx is not None:
            trig = triggers[pid]
            trig_text = yaml.safe_dump(
                {"trigger": trig}, allow_unicode=True, sort_keys=False, default_flow_style=False
            ).rstrip("\n")
            # safe_dump 输出 "trigger:\n  scenes:\n  - ..."，整体再缩进 2 空格
            indent_block = "\n".join(
                "  " + bl if bl.strip() else bl for bl in trig_text.split("\n")
            )
            # 在 confidence 行之后插入
            block = block[: conf_idx + 1] + [indent_block] + block[conf_idx + 1 :]
            inserted.add(pid)
            merged_count += 1
        out.extend(block)
        i = j

    missing = set(triggers.keys()) - inserted
    if missing:
        print(f"警告：以下原则未找到插入点（可能无 confidence 行）: {sorted(missing)}")

    if merged_count == 0:
        print("错误：未合并任何 trigger，中止（不写回）")
        return 1

    if backup:
        bak = model_path.with_suffix(model_path.suffix + ".bak")
        shutil.copy2(model_path, bak)
        print(f"备份: {bak}")

    model_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"合并完成：{merged_count} 条 trigger 已写入 {model_path}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--triggers", required=True)
    ap.add_argument("--backup", action="store_true")
    args = ap.parse_args()
    sys.exit(merge(Path(args.model), Path(args.triggers), args.backup))
