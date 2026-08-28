# -*- coding: utf-8 -*-
"""Person Method Model Schema 校验脚本（scripts/validate_schema.py）的测试。

覆盖:
    1. 合法 method yaml（1 person + 1 source + 1 principle + 1 case）→ 校验通过
    2. 缺 principle.statement / evidence 为空 → 校验失败
    3. 枚举越界、跨实体引用无效 → 校验失败
"""

import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATE_SCRIPT = PROJECT_ROOT / "scripts" / "validate_schema.py"


def _run_validator(method_doc, tmp_path):
    """把 method 文档写入临时 yaml，调用校验脚本，返回 (returncode, stderr)"""
    method_file = tmp_path / "method.yaml"
    method_file.write_text(
        yaml.safe_dump(method_doc, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(VALIDATE_SCRIPT), str(method_file)],
        timeout=120,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stderr


def _valid_doc():
    """构造一个合法的最小 method 文档（1 person + 1 source + 1 principle + 1 case）"""
    return {
        "method_version": "v0.1",
        "person": {"id": "jack-welch", "name": "杰克·韦尔奇", "domain": "企业管理"},
        "sources": [
            {
                "id": "winning",
                "type": "book",
                "title": "《赢》",
                "file": "corpus/books/winning.md",
                "date": 2005,
            }
        ],
        "principles": [
            {
                "id": "candor",
                "statement": "坦诚是组织效率的基石",
                "confidence": "high",
                "evidence": [
                    {"source": "winning", "loc": "ch2", "quote": "……", "level": "E4"}
                ],
            }
        ],
        "cases": [
            {
                "id": "ge_business_x",
                "context": "……",
                "problem": "……",
                "decision": "……",
                "action": "……",
                "outcome": "……",
                "reasoning": "……",
                "principle": ["candor"],
            }
        ],
    }


def test_valid_method_passes(tmp_path):
    """合法文档：校验通过（退出码 0）"""
    code, stderr = _run_validator(_valid_doc(), tmp_path)
    assert code == 0, f"合法文档不应报错: {stderr}"


def test_missing_required_field_fails(tmp_path):
    """缺 principle.statement：校验失败（退出码 1），错误信息含字段名"""
    doc = _valid_doc()
    del doc["principles"][0]["statement"]
    code, stderr = _run_validator(doc, tmp_path)
    assert code == 1
    assert "statement" in stderr


def test_empty_evidence_fails(tmp_path):
    """principle.evidence 为空数组：校验失败"""
    doc = _valid_doc()
    doc["principles"][0]["evidence"] = []
    code, stderr = _run_validator(doc, tmp_path)
    assert code == 1
    assert "evidence" in stderr


def test_enum_out_of_range_fails(tmp_path):
    """confidence 枚举越界：校验失败"""
    doc = _valid_doc()
    doc["principles"][0]["confidence"] = "very-high"
    code, _ = _run_validator(doc, tmp_path)
    assert code == 1


def test_invalid_evidence_source_reference_fails(tmp_path):
    """evidence.source 引用不存在的 source：校验失败"""
    doc = _valid_doc()
    doc["principles"][0]["evidence"][0]["source"] = "no-such-source"
    code, stderr = _run_validator(doc, tmp_path)
    assert code == 1
    assert "no-such-source" in stderr


def test_invalid_case_principle_reference_fails(tmp_path):
    """case.principle 引用不存在的 principle：校验失败"""
    doc = _valid_doc()
    doc["cases"][0]["principle"] = ["ghost-principle"]
    code, stderr = _run_validator(doc, tmp_path)
    assert code == 1
    assert "ghost-principle" in stderr
