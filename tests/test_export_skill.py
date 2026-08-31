# -*- coding: utf-8 -*-
"""export_skill.py 导出器测试（使用示例模型，不依赖真实人物/LLM）。"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EXAMPLE_MODEL = PROJECT_ROOT / "data" / "methods" / "example" / "person-example-v0.1.yaml"


def _export(tmp_path: Path) -> Path:
    out = tmp_path / "example-method"
    r = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "export_skill.py"),
         "--model", str(EXAMPLE_MODEL), "--out", str(out)],
        capture_output=True, text=True)
    assert r.returncode == 0, f"导出失败：{r.stderr[-500:]}"
    return out


def test_export_produces_all_files(tmp_path):
    out = _export(tmp_path)
    assert (out / "SKILL.md").is_file()
    for ref in ("principles", "rules", "cases", "diagnostics"):
        assert (out / "references" / f"{ref}.md").is_file(), f"缺 references/{ref}.md"


def test_frontmatter_valid(tmp_path):
    out = _export(tmp_path)
    md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert md.startswith("---\n"), "frontmatter 必须以 --- 开头"
    assert 'name: example-method' in md, "name 应为 <person-id>-method"
    assert 'description: "' in md, "必须有 description（agent 触发判断用）"
    # description 长度规范（Claude Code：≤1024 字符）
    desc_line = [l for l in md.splitlines() if l.startswith("description:")][0]
    assert len(desc_line) <= 1024 + 20, "description 超长"


def test_no_template_leftovers(tmp_path):
    out = _export(tmp_path)
    md = (out / "SKILL.md").read_text(encoding="utf-8")
    assert "通用模板" not in md, "模板说明头不应出现在产物"
    assert "{{" not in md, "占位符未替换干净"
    assert "示例人物" in md, "人物名应渲染进 SKILL.md"


def test_references_content(tmp_path):
    out = _export(tmp_path)
    principles = (out / "references" / "principles.md").read_text(encoding="utf-8")
    assert "聚焦主业" in principles, "原则应渲染"
    assert "力出一孔" in principles, "证据 quote 应渲染"
    assert "不应触发" in principles, "trigger.not_for 应渲染（防万能原则）"
    diagnostics = (out / "references" / "diagnostics.md").read_text(encoding="utf-8")
    assert "诊断路径" in diagnostics
    rules = (out / "references" / "rules.md").read_text(encoding="utf-8")
    assert "危机留现金" in rules and "例外" in rules


def test_missing_model_reports_clear_error(tmp_path):
    r = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "export_skill.py"),
         "--model", "/nonexistent/model.yaml", "--out", str(tmp_path / "x")],
        capture_output=True, text=True)
    assert r.returncode != 0
    assert "不存在" in r.stderr or "不存在" in r.stdout, "应有清晰中文报错"
