#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Method Advisor — 语料层转换管线

功能: 把单个语料文件转换为 Markdown，输出到
      data/sources/<person>/<type>/<slug>.md，
      并在文件头部自动生成 YAML frontmatter（source/type/converter/converted_at）。

转换器选择（按优先级）:
    1. anydoc（首选）: doc/docx/ppt/pptx/xls/xlsx/odt/ods/odp/rtf/epub/csv/文本型 PDF
    2. markitdown（回退）: 图片 OCR、音频等 anydoc 不支持的格式（若已安装）
    3. 扫描型 PDF: anydoc 返回 Unsupported → 提示用户用 MinerU 处理（不自动调用）

用法:
    python3 scripts/convert.py <file> --person <id> [--type book|article|speech|case]

退出码:
    0 = 转换成功
    1 = 转换失败
    2 = 需要人工介入（扫描型 PDF，需 MinerU）
"""

import argparse
import datetime
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANYDOC_PATH = Path(os.environ.get("ANYDOC_PATH", str(Path.home() / ".npm-global/bin/anydoc")))
CONVERT_TIMEOUT = 120  # 外部命令超时（秒）

VALID_TYPES = ("book", "article", "speech", "case")

# 纯文本格式：无需转换器，直接读取加 frontmatter
TEXT_FORMATS = {".txt", ".md", ".markdown", ".rst", ".adoc"}


class ConversionError(Exception):
    """转换失败（所有可用转换器均无法处理）"""


class ScannedPdfError(ConversionError):
    """扫描型 PDF：anydoc 不支持，需要人工使用 MinerU 处理"""


def make_slug(filename: str) -> str:
    """由文件名生成 slug：去扩展名、非字母数字转 '-'、小写（保留中文等 Unicode 字符）"""
    stem = Path(filename).stem
    slug = re.sub(r"[^\w]+", "-", stem.lower()).strip("-")
    slug = slug.replace("_", "-")
    return slug or "untitled"


def infer_type(filename: str) -> str:
    """根据文件名启发式推断语料类型（--type 缺省时使用）"""
    name = filename.lower()
    if any(k in name for k in ("演讲", "访谈", "speech", "interview")):
        return "speech"
    if any(k in name for k in ("案例", "case")):
        return "case"
    if any(k in name for k in ("书", "book")):
        return "book"
    return "article"


def markitdown_available() -> bool:
    """检测 markitdown 模块是否已安装"""
    return importlib.util.find_spec("markitdown") is not None


def convert_with_anydoc(file_path: Path) -> str:
    """首选转换器：anydoc，markdown 输出到 stdout"""
    try:
        result = subprocess.run(
            [str(ANYDOC_PATH), str(file_path)],
            timeout=CONVERT_TIMEOUT,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise ConversionError(f"找不到 anydoc 可执行文件: {ANYDOC_PATH}，请先安装 anydoc") from None
    except subprocess.TimeoutExpired:
        raise ConversionError(f"anydoc 转换超时（超过 {CONVERT_TIMEOUT} 秒）: {file_path.name}") from None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if "unsupported" in detail.lower() and file_path.suffix.lower() == ".pdf":
            raise ScannedPdfError(
                f"anydoc 不支持该文件类型（可能是扫描型 PDF）: {detail[:200]}"
            )
        raise ConversionError(
            f"anydoc 转换失败（退出码 {result.returncode}）: {detail[:500]}"
        )
    return result.stdout


def convert_with_markitdown(file_path: Path) -> str:
    """回退转换器：markitdown（python3 -m markitdown <file>）"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "markitdown", str(file_path)],
            timeout=CONVERT_TIMEOUT,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise ConversionError("找不到 markitdown 模块（python3 -m markitdown 不可用）") from None
    except subprocess.TimeoutExpired:
        raise ConversionError(f"markitdown 转换超时（超过 {CONVERT_TIMEOUT} 秒）: {file_path.name}") from None

    if result.returncode != 0:
        detail_lines = [line for line in (result.stderr or result.stdout or "").splitlines() if line.strip()]
        # 只保留最后一行关键信息（跳过冗长的 traceback）
        detail = (detail_lines[-1] if detail_lines else "")[:300]
        raise ConversionError(f"markitdown 转换失败（退出码 {result.returncode}）: {detail}")
    return result.stdout


def convert_file(file_path: Path, person: str, doc_type: str) -> tuple[Path, str]:
    """
    执行转换并写入 data/sources/<person>/<type>/<slug>.md。

    返回 (输出文件绝对路径, 实际使用的转换器名称)。
    扫描型 PDF 会抛出 ScannedPdfError（不自动回退 markitdown）。
    """
    if file_path.suffix.lower() in TEXT_FORMATS:
        # 纯文本：直接读取，无需转换器
        markdown = file_path.read_text(encoding="utf-8", errors="replace")
        converter = "text"
    else:
        try:
            markdown = convert_with_anydoc(file_path)
            converter = "anydoc"
        except ScannedPdfError:
            raise  # 扫描版 PDF：提示 MinerU，不自动回退
        except ConversionError as anydoc_err:
            if not markitdown_available():
                raise anydoc_err  # 无回退转换器可用，原样抛出
            print(f"[提示] anydoc 失败，尝试回退 markitdown：{anydoc_err}", file=sys.stderr)
            markdown = convert_with_markitdown(file_path)
            converter = "markitdown"

    output_dir = PROJECT_ROOT / "data" / "sources" / person / doc_type
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{make_slug(file_path.name)}.md"

    now = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    frontmatter = (
        "---\n"
        f"source: {file_path.name}\n"
        f"type: {doc_type}\n"
        f"converter: {converter}\n"
        f"converted_at: {now}\n"
        "---\n\n"
    )
    output_file.write_text(frontmatter + markdown.lstrip(), encoding="utf-8")
    return output_file, converter


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Method Advisor 语料层转换管线：单文件 → Markdown（anydoc 优先 / markitdown 回退）"
    )
    parser.add_argument("file", help="待转换的语料文件（doc/docx/ppt/pptx/xls/xlsx/odt/ods/odp/rtf/epub/csv/pdf/图片/音频等）")
    parser.add_argument("--person", required=True, help="人物 ID（如 jack-welch），决定输出目录 data/sources/<person>/")
    parser.add_argument(
        "--type",
        choices=VALID_TYPES,
        help="语料类型（缺省时按文件名启发式推断: 演讲/访谈→speech, 案例→case, 书→book, 否则 article）",
    )
    args = parser.parse_args(argv)

    file_path = Path(args.file).resolve()
    if not file_path.is_file():
        print(f"[错误] 输入文件不存在: {file_path}", file=sys.stderr)
        return 1

    doc_type = args.type or infer_type(file_path.name)
    try:
        output_file, converter = convert_file(file_path, args.person, doc_type)
    except ScannedPdfError:
        print(
            "[提示] anydoc 不支持该文件（可能是扫描型 PDF）。请使用 MinerU 处理扫描版后再转换"
            "（本项目不自动调用 MinerU）。",
            file=sys.stderr,
        )
        return 2
    except ConversionError as e:
        print(f"[错误] 转换失败: {e}", file=sys.stderr)
        return 1

    print(f"转换完成: {output_file}（converter: {converter}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
