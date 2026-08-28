#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method Advisor — Person Method Model Schema v0.1 校验脚本

用法:
    python3 scripts/validate_schema.py <method.yaml>

校验内容:
    1. JSON Schema 结构校验（必填字段缺失、类型错误、枚举越界、数组最小长度等）
    2. 跨实体引用校验:
       - evidence.source       → 必须存在于 sources[].id
       - case.principle[]      → 必须存在于 principles[].id
       - tension.a / tension.b → 必须存在于 principles[].id

退出码:
    0 = 校验通过
    1 = 校验失败或运行错误（错误列表输出到 stderr）
"""

import argparse
import sys
from pathlib import Path

import jsonschema
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "method.schema.yaml"


def _format_path(error) -> str:
    """把 jsonschema 的错误路径（如 ['principles', 0, 'statement']）格式化为 principles[0].statement"""
    parts = []
    for item in error.absolute_path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            parts.append(f".{item}")
    text = "".join(parts).lstrip(".")
    return text or "<根>"


def _format_error(error) -> str:
    """把 jsonschema 校验错误翻译为中文可读信息"""
    validator = error.validator
    path = _format_path(error)
    if validator == "required":
        missing = ", ".join(str(name) for name in error.validator_value)
        return f"{path}: 缺少必填字段 {missing}"
    if validator == "type":
        return f"{path}: 类型错误，期望 {error.validator_value}，实际为 {type(error.instance).__name__}"
    if validator == "enum":
        return f"{path}: 枚举越界，取值 {error.instance!r} 不在允许范围 {error.validator_value}"
    if validator == "minItems":
        return f"{path}: 数组元素不足，至少需要 {error.validator_value} 个"
    if validator == "additionalProperties":
        return f"{path}: 包含未定义的字段 {error.validator_value}"
    if validator == "minLength":
        return f"{path}: 字符串长度不足（至少 {error.validator_value} 个字符）"
    return f"{path}: {error.message}"


def _check_references(doc, errors: list) -> None:
    """跨实体引用校验：evidence / case / tension 引用的 ID 必须真实存在"""
    sources = doc.get("sources") or []
    principles = doc.get("principles") or []
    source_ids = {s.get("id") for s in sources if isinstance(s, dict)}
    principle_ids = {p.get("id") for p in principles if isinstance(p, dict)}

    # evidence.source → sources[].id（principle 与 rule 内的证据链）
    for i, p in enumerate(principles):
        if not isinstance(p, dict):
            continue
        for j, ev in enumerate(p.get("evidence") or []):
            if isinstance(ev, dict) and ev.get("source") not in source_ids:
                errors.append(f"principles[{i}].evidence[{j}].source 引用了不存在的 source: {ev.get('source')!r}")
    for i, r in enumerate(doc.get("rules") or []):
        if not isinstance(r, dict):
            continue
        for j, ev in enumerate(r.get("evidence") or []):
            if isinstance(ev, dict) and ev.get("source") not in source_ids:
                errors.append(f"rules[{i}].evidence[{j}].source 引用了不存在的 source: {ev.get('source')!r}")

    # case.principle[] → principles[].id
    for i, c in enumerate(doc.get("cases") or []):
        if not isinstance(c, dict):
            continue
        for j, pid in enumerate(c.get("principle") or []):
            if pid not in principle_ids:
                errors.append(f"cases[{i}].principle[{j}] 引用了不存在的 principle: {pid!r}")

    # tension.a / tension.b → principles[].id
    for i, t in enumerate(doc.get("tensions") or []):
        if not isinstance(t, dict):
            continue
        for field in ("a", "b"):
            ref = t.get(field)
            if ref and ref not in principle_ids:
                errors.append(f"tensions[{i}].{field} 引用了不存在的 principle: {ref!r}")

    # trigger 结构检查：principle.trigger 若存在，scenes/signals 至少一个非空（v0.2 新增）
    for i, p in enumerate(principles):
        trig = p.get("trigger")
        if trig is None:
            continue
        if not isinstance(trig, dict):
            errors.append(f"principles[{i}].trigger 类型错误，期望 object，实际为 {type(trig).__name__}")
            continue
        scenes = trig.get("scenes") or []
        signals = trig.get("signals") or []
        if not scenes and not signals:
            errors.append(f"principles[{i}].trigger（{p.get('id', '?')}）：scenes/signals 至少填一个")
        if not isinstance(scenes, list) or any(not isinstance(s, str) or not s.strip() for s in scenes):
            errors.append(f"principles[{i}].trigger.scenes 应为非空字符串列表")
        if not isinstance(signals, list) or any(not isinstance(s, str) or not s.strip() for s in signals):
            errors.append(f"principles[{i}].trigger.signals 应为非空字符串列表")
        nf = trig.get("not_for")
        if nf is not None and (not isinstance(nf, list) or any(not isinstance(s, str) or not s.strip() for s in nf)):
            errors.append(f"principles[{i}].trigger.not_for 应为字符串列表")


def validate_file(method_path: Path, schema_path: Path = DEFAULT_SCHEMA) -> tuple[list, int]:
    """
    校验一个 method YAML 文件。

    返回 (errors, exit_code)：
        errors 为空且 exit_code=0 表示通过；
        出错时 errors 为中文错误列表，exit_code=1。
    """
    try:
        with open(method_path, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
    except FileNotFoundError:
        return [f"找不到待校验文件: {method_path}"], 1
    except yaml.YAMLError as e:
        return [f"method YAML 解析失败: {e}"], 1

    try:
        with open(schema_path, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
    except FileNotFoundError:
        return [f"找不到 Schema 文件: {schema_path}"], 1

    if not isinstance(doc, dict) or not doc:
        return ["method 文件为空或顶层不是对象"], 1

    errors = []
    validator = jsonschema.Draft7Validator(schema)
    for error in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        errors.append(_format_error(error))
    _check_references(doc, errors)

    return errors, (0 if not errors else 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="校验 Method Advisor Person Method Model YAML（Schema v0.1）"
    )
    parser.add_argument("method_file", help="待校验的 method YAML 文件路径")
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA),
        help=f"Schema 文件路径（默认: {DEFAULT_SCHEMA}）",
    )
    args = parser.parse_args(argv)

    errors, exit_code = validate_file(Path(args.method_file), Path(args.schema))
    if errors:
        print(f"校验失败，共 {len(errors)} 个错误：", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
    else:
        print("校验通过 ✓")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
