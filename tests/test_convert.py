# -*- coding: utf-8 -*-
"""语料层转换管线（scripts/convert.py）的测试。

覆盖:
    1. 实测转换 docx → markdown，断言输出文件存在、frontmatter 完整、正文非空
    2. slug 生成 / 类型启发式推断的单测
"""

import subprocess
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import convert  # noqa: E402   （import 顺序在 sys.path 调整之后）

CONVERT_SCRIPT = PROJECT_ROOT / "scripts" / "convert.py"

# 测试语料：优先使用任务指定的 docx；不可用时回退到任意现成 .docx/.md
TEST_DOCX = Path(os.environ.get("TEST_DOCX", str(PROJECT_ROOT / "refs" / "sample.docx")))
FALLBACK_ROOTS = [PROJECT_ROOT / "refs"]


def _find_fallback_doc():
    for root in FALLBACK_ROOTS:
        for pattern in ("*.docx", "*.md"):
            hits = sorted(root.rglob(pattern))
            if hits:
                return hits[0]
    return None


@pytest.fixture(scope="module")
def source_doc():
    """返回可用的测试语料文件路径，找不到则跳过"""
    doc = TEST_DOCX if TEST_DOCX.is_file() else _find_fallback_doc()
    if doc is None:
        pytest.skip("未找到可用的测试语料（.docx/.md）")
    return doc


def test_docx_to_markdown_conversion(tmp_path, source_doc):
    """实测转换：输出文件存在、frontmatter 完整、正文非空"""
    person = "test-person"
    doc_type = "article"

    result = subprocess.run(
        [
            sys.executable,
            str(CONVERT_SCRIPT),
            str(source_doc),
            "--person",
            person,
            "--type",
            doc_type,
        ],
        timeout=180,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"转换失败（退出码 {result.returncode}）: {result.stderr}"

    # 断言输出文件存在（路径与 convert.make_slug 的计算一致）
    output_file = (
        PROJECT_ROOT / "data" / "sources" / person / doc_type / f"{convert.make_slug(source_doc.name)}.md"
    )
    assert output_file.is_file(), f"输出文件不存在: {output_file}"
    text = output_file.read_text(encoding="utf-8")

    # 断言 frontmatter 完整（source / type / converter / converted_at）
    assert text.startswith("---\n"), "输出缺少 YAML frontmatter 起始标记"
    frontmatter = text.split("---\n", 2)[1]
    for key in ("source:", "type:", "converter:", "converted_at:"):
        assert key in frontmatter, f"frontmatter 缺少字段 {key}"
    assert f"type: {doc_type}" in frontmatter
    assert f"source: {source_doc.name}" in frontmatter

    # 断言正文非空
    body = text.split("---\n", 2)[2].strip()
    assert body, "转换结果正文为空"


def test_markitdown_fallback_direct(source_doc):
    """回退路径：直接调用 markitdown 转换器，应产出非空 markdown（模块未安装时跳过）"""
    if not convert.markitdown_available():
        pytest.skip("markitdown 未安装，跳过回退路径测试")
    md = convert.convert_with_markitdown(Path(source_doc))
    assert md.strip(), "markitdown 转换结果为空"


def test_make_slug():
    """slug 生成规则：去扩展名、非字母数字转 '-'、小写（保留中文）"""
    assert convert.make_slug("智商税思考框架.docx") == "智商税思考框架"
    assert convert.make_slug("My File (v2).docx") == "my-file-v2"
    assert convert.make_slug("a_b c.md") == "a-b-c"
    assert convert.make_slug("---.docx") == "untitled"  # 全为分隔符时兜底


def test_infer_type_heuristics():
    """类型启发式推断：演讲/访谈→speech，案例→case，书→book，否则 article"""
    assert convert.infer_type("王兴演讲实录.docx") == "speech"
    assert convert.infer_type("某公司案例研究.md") == "case"
    assert convert.infer_type("商业模式的书.pdf") == "book"
    assert convert.infer_type("随便一篇文章.txt") == "article"
